"""Downloads, verified updates, Proton profiles and versioned folder saves."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import urllib.request
import zipfile

REPO = 'https://api.github.com/repos/Sttanors/orbit-launcher'
DOWNLOAD = 'https://github.com/Sttanors/orbit-launcher/releases/download/'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def proton_versions(roots):
    paths = [Path.home() / '.steam/root/compatibilitytools.d', Path.home() / '.local/share/Steam/compatibilitytools.d']
    for root in roots:
        paths.extend([root / 'compatibilitytools.d', root / 'steamapps/common'])
        config = root / 'steamapps/libraryfolders.vdf'
        if config.exists():
            paths.extend(Path(p.replace('\\\\', '\\')) / 'steamapps/common' for p in re.findall(r'"path"\s*"([^"\n]+)"', config.read_text(errors='replace')))
    found = {}
    for folder in paths:
        if folder.is_dir():
            for script in folder.glob('*/proton'):
                if script.is_file():
                    found[str(script.resolve())] = {'path': str(script.resolve()), 'name': script.parent.name}
    return sorted(found.values(), key=lambda p: p['name'].lower())


def game_command(game, data, roots, windows=False):
    path = Path(game['path'])
    environment = os.environ.copy()
    if game.get('runner', 'native') == 'proton' and not windows:
        proton = Path(game.get('proton', ''))
        if not proton.is_file() or proton.name != 'proton':
            raise ValueError('Выбери установленную версию Proton в параметрах игры.')
        if not roots:
            raise ValueError('Для Proton нужна установленная версия Steam.')
        prefix = Path(data) / 'prefixes' / game['id']
        prefix.mkdir(parents=True, exist_ok=True)
        environment.update(STEAM_COMPAT_DATA_PATH=str(prefix.resolve()), STEAM_COMPAT_CLIENT_INSTALL_PATH=str(roots[0]), SteamAppId='0', SteamGameId='0')
        # Unfreeze the environment inherited from PyInstaller before calling system Python/Wine.
        if getattr(sys, 'frozen', False):
            environment['LD_LIBRARY_PATH'] = environment.get('LD_LIBRARY_PATH_ORIG', '')
        return [str(proton), 'waitforexitandrun', str(path)], environment
    if not windows and not os.access(path, os.X_OK):
        raise ValueError('Нет права на запуск. Для .exe на Linux выбери Proton.')
    return [str(path)], environment


class SaveConflict(ValueError):
    pass


class Saves:
    """Immutable ZIP snapshots in an already synced folder. Never delete save files."""
    def __init__(self, data):
        self.data = Path(data)

    def locations(self, profile):
        local = Path(profile.get('local', '')).expanduser().resolve()
        cloud = Path(profile.get('cloud', '')).expanduser().resolve()
        key = profile.get('key', '')
        if not profile.get('local') or not profile.get('cloud') or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', key):
            raise ValueError('Укажи папку сохранений, папку облака и общий ключ игры (латиница, цифры, - или _).')
        if local == self.data.resolve() or local in self.data.resolve().parents:
            raise ValueError('Папка сохранений не должна содержать данные Orbit.')
        if local == cloud or local in cloud.parents or cloud in local.parents:
            raise ValueError('Папки сохранений и облака не должны находиться друг в друге.')
        if not local.is_dir() or not cloud.is_dir():
            raise ValueError('Папка сохранений или облака недоступна. Подключи диск и повтори.')
        return local, cloud / 'Orbit-Saves' / key

    def inventory(self, local):
        files = {}
        for path in sorted(local.rglob('*')):
            if path.is_symlink():
                raise ValueError('В папке сохранений есть ссылка. Выбери папку с обычными файлами.')
            if path.is_file():
                files[path.relative_to(local).as_posix()] = digest(path)
        return files

    def history(self, profile):
        _, remote = self.locations(profile)
        result = []
        for manifest in remote.glob('*.json'):
            try:
                item = json.loads(manifest.read_text(encoding='utf-8'))
                if re.fullmatch(r'[0-9a-f]{32}', item['id']) and (remote / (item['id'] + '.zip')).is_file():
                    result.append(item)
            except (ValueError, KeyError, OSError):
                continue
        return sorted(result, key=lambda v: (v['time'], v['id']), reverse=True)

    def snapshot(self, local, remote, files):
        remote.mkdir(parents=True, exist_ok=True)
        sid = uuid.uuid4().hex
        part = remote / (sid + '.part')
        with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, expected in files.items():
                path = local / name
                archive.write(path, name)
                if digest(path) != expected:
                    part.unlink(missing_ok=True)
                    raise ValueError('Сохранение меняется. Закрой игру и повтори синхронизацию.')
        part.replace(remote / (sid + '.zip'))
        item = {'id': sid, 'time': time.time(), 'files': files, 'sha256': digest(remote / (sid + '.zip'))}
        atomic_json(remote / (sid + '.json'), item)
        return item

    def restore(self, local, remote, item):
        archive = remote / (item['id'] + '.zip')
        if digest(archive) != item['sha256']:
            raise ValueError('Копия в облаке ещё не скачана полностью или повреждена.')
        # Validate and stage every file before touching a live save.
        stage = self.data / 'save-stage' / uuid.uuid4().hex
        stage.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive) as source:
                for name, expected in item['files'].items():
                    relative = Path(name)
                    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                        raise ValueError('Недопустимый путь в сохранении.')
                    destination = stage / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(name) as src, destination.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    if digest(destination) != expected:
                        raise ValueError('Повреждённый файл в копии сохранения.')
            backup = self.data / 'save-backups' / uuid.uuid4().hex
            shutil.copytree(local, backup)
            for name in item['files']:
                target = local / name
                if any(p.is_symlink() for p in [target, *target.parents]):
                    raise ValueError('Путь сохранения содержит ссылку.')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage / name, target)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def sync(self, game_id, profile, choice='', snapshot_id=''):
        local, remote = self.locations(profile)
        baseline_path = self.data / 'save-baselines' / (game_id + '.json')
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        files = self.inventory(local)
        history = self.history(profile)
        latest = history[0] if history else None
        if snapshot_id:
            latest = next((v for v in history if v['id'] == snapshot_id), None)
            if not latest:
                raise ValueError('Копия не найдена.')
            choice = 'cloud'
        if choice == 'cloud' and not latest:
            raise ValueError('В облаке пока нет сохранений.')
        remote_files = latest['files'] if latest else None
        if choice not in ('', 'local', 'cloud'):
            raise ValueError('Неизвестный вариант конфликта.')
        if files == remote_files:
            pass
        elif choice == 'cloud' or (choice == '' and latest and (files == baseline or not files)):
            self.restore(local, remote, latest)
            files = self.inventory(local)
            if snapshot_id or files != latest['files']:
                latest = self.snapshot(local, remote, files)
        elif choice == 'local' or latest is None or (baseline is not None and remote_files == baseline):
            latest = self.snapshot(local, remote, files)
        else:
            raise SaveConflict('Сохранения на компьютере и в облаке отличаются. Выбери версию в меню «Сохранения».')
        atomic_json(baseline_path, files)
        return {'ok': True, 'message': 'Сохранения синхронизированы', 'history': self.history(profile)}


def user_install_root():
    if not getattr(sys, 'frozen', False) or sys.platform == 'win32':
        return None
    root=Path(sys.executable).resolve().parent.parent
    return root if root.is_relative_to(Path.home().resolve()) and (root/'.orbit-user-install.json').is_file() else None


def install_user_bundle(package, root, version):
    """Install a verified native release payload into a versioned user directory."""
    import tempfile
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.stage-',dir=root) as temp:
        subprocess.run(['tar','--zstd','-xf',str(package),'-C',temp,'opt/orbit'],check=True,timeout=180)
        payload=Path(temp)/'opt/orbit'
        binary=payload/'orbit'
        result=subprocess.run([str(binary),'--version'],capture_output=True,text=True,check=True,timeout=30,env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'})
        if result.stdout.strip()!=version:
            raise ValueError('Версия внутри пакета не совпала с релизом.')
        target=root/version
        if target.exists():
            target.rename(root/(version+'-previous-'+uuid.uuid4().hex[:8]))
        shutil.move(str(payload),str(target))
        atomic_json(root/'.orbit-user-install.json',{'layout':1})
        link=root/('.current-'+uuid.uuid4().hex)
        link.symlink_to(target.name,target_is_directory=True)
        link.replace(root/'current')
    return root/'current/orbit'


class Updater:
    def __init__(self, data, version):
        self.data, self.version, self.release, self.ready = Path(data), version, None, None

    def fetch_json(self, url):
        request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Orbit-Launcher'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def check(self):
        release = self.fetch_json(REPO + '/releases/latest')
        version = release['tag_name'].removeprefix('v')
        if not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Неизвестный формат версии релиза.')
        self.release = release
        return {'version': version, 'current': self.version, 'available': tuple(map(int, version.split('.'))) > tuple(map(int, self.version.split('.'))), 'notes': release.get('body', '')}

    def package(self):
        if user_install_root():
            return 'x86_64.pkg.tar.zst', 'SHA256SUMS-linux.txt'
        if sys.platform == 'win32':
            return 'windows-x64-setup.exe', 'SHA256SUMS-windows.txt'
        # Prefer the installed package manager database, not a stray executable.
        if Path('/var/lib/pacman/local').exists():
            return 'x86_64.pkg.tar.zst', 'SHA256SUMS-linux.txt'
        if Path('/var/lib/dpkg/status').exists():
            return '_amd64.deb', 'SHA256SUMS-linux.txt'
        if shutil.which('rpm'):
            return 'x86_64.rpm', 'SHA256SUMS-linux.txt'
        raise ValueError('Автоустановка поддерживает Windows, Debian/Ubuntu, Fedora и Arch. Открой релиз на GitHub.')

    def download(self):
        self.ready = None
        check = self.check()
        if not check['available']:
            raise ValueError('Установлена последняя версия Orbit.')
        suffix, checksums = self.package()
        assets = self.release['assets']
        asset = next((a for a in assets if a['name'].endswith(suffix)), None)
        sums = next((a for a in assets if a['name'] == checksums), None)
        if not asset or not sums:
            raise ValueError('В релизе нет пакета для этой системы.')
        def url(item):
            value = item['browser_download_url']
            if not value.startswith(DOWNLOAD) or Path(item['name']).name != item['name']:
                raise ValueError('Недопустимый адрес обновления.')
            return value
        with urllib.request.urlopen(url(sums), timeout=30) as response:
            entries = response.read(1024 * 1024).decode().splitlines()
        expected = next((line.split()[0] for line in entries if len(line.split()) == 2 and line.split()[1].lstrip('*') == asset['name']), '')
        if not re.fullmatch('[a-fA-F0-9]{64}', expected):
            raise ValueError('Контрольная сумма пакета не найдена.')
        folder = self.data / 'updates'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / asset['name']
        part = target.with_suffix(target.suffix + '.part')
        try:
            with urllib.request.urlopen(url(asset), timeout=60) as src, part.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if digest(part).lower() != expected.lower():
                raise ValueError('Контрольная сумма обновления не совпала.')
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
        self.ready = target
        self.ready_hash = expected.lower()
        return {'ok': True, 'message': 'Обновление проверено. Нажми «Установить и перезапустить».', 'ready': True}

    def install(self):
        if not self.ready or not self.ready.is_file():
            raise ValueError('Сначала скачай и проверь обновление.')
        target = self.ready
        if digest(target).lower() != self.ready_hash:
            self.ready = None
            raise ValueError('Пакет изменился после проверки. Скачай обновление заново.')
        install_root=user_install_root()
        if install_root:
            import shlex
            executable=install_user_bundle(target,install_root,self.release['tag_name'].removeprefix('v'))
            script=self.data/'updates/restart.sh'
            script.write_text('#!/bin/sh\nwhile kill -0 '+str(os.getpid())+' 2>/dev/null; do sleep 1; done\nexec '+shlex.quote(str(executable))+'\n',encoding='utf-8')
            subprocess.Popen(['/bin/sh',str(script)],start_new_session=True)
        elif sys.platform == 'win32':
            subprocess.Popen([str(target), '/SP-', '/SILENT', '/CLOSEAPPLICATIONS', '/RESTARTAPPLICATIONS'], creationflags=subprocess.DETACHED_PROCESS)
        else:
            if not shutil.which('pkexec'):
                raise ValueError('Для установки нужен polkit (pkexec). Пакет сохранён в ' + str(target))
            command = ['dpkg', '-i'] if target.suffix == '.deb' else ['rpm', '-U'] if target.suffix == '.rpm' else ['pacman', '-U', '--noconfirm']
            import shlex
            script = self.data / 'updates/install.sh'
            script.write_text('#!/bin/sh\nwhile kill -0 ' + str(os.getpid()) + ' 2>/dev/null; do sleep 1; done\npkexec ' + shlex.join([*command, str(target)]) + '\nstatus=$?\norbit\nexit "$status"\n', encoding='utf-8')
            subprocess.Popen(['/bin/sh', str(script)], start_new_session=True)
        return {'ok': True}


class Torrents:
    def __init__(self, data):
        self.data = Path(data) / 'torrents'
        self.session = None
        self.entries = {}
        self.handles = {}
        self.error = ''
        self.validated = set()

    def start(self):
        if self.session:
            return
        import libtorrent as lt
        self.lt = lt
        self.data.mkdir(parents=True, exist_ok=True)
        self.session = lt.session({'listen_interfaces': '0.0.0.0:6881,[::]:6881', 'active_downloads': 2, 'active_seeds': 1, 'active_limit': 3, 'enable_upnp': False, 'enable_natpmp': False})
        state = self.data / 'queue.json'
        if state.exists():
            for entry in json.loads(state.read_text(encoding='utf-8')):
                try:
                    self._add(entry)
                except (RuntimeError, ValueError, OSError) as error:
                    self.error = str(error)

    def save(self):
        atomic_json(self.data / 'queue.json', list(self.entries.values()))

    def _add(self, entry):
        lt = self.lt
        if not Path(entry['path']).is_dir():
            raise ValueError('Папка загрузки недоступна: ' + entry['path'])
        source = entry['source']
        params = lt.parse_magnet_uri(source) if source.startswith('magnet:?') else lt.add_torrent_params()
        if not source.startswith('magnet:?'):
            params.ti = lt.torrent_info(source)
            storage = params.ti.files()
            for i in range(storage.num_files()):
                path = Path(storage.file_path(i))
                if path.is_absolute() or '..' in path.parts or storage.file_flags(i) & lt.file_storage.flag_symlink:
                    raise ValueError('Торрент содержит недопустимый путь или ссылку.')
        if source.startswith('magnet:?'):
            params.flags |= lt.torrent_flags.upload_mode
        params.save_path = entry['path']
        params.flags |= lt.torrent_flags.auto_managed
        if entry.get('paused'):
            params.flags &= ~lt.torrent_flags.auto_managed
            params.flags |= lt.torrent_flags.paused
        else:
            params.flags &= ~lt.torrent_flags.paused
        handle = self.session.add_torrent(params)
        if any(h == handle for h in self.handles.values()):
            raise ValueError('Эта загрузка уже есть в очереди.')
        self.entries[entry['id']] = entry
        self.handles[entry['id']] = handle
        if not source.startswith('magnet:?'):
            self.validated.add(entry['id'])

    def add(self, source, destination, auto_add=True):
        self.start()
        path = Path(destination).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('Выбери существующую папку загрузки.')
        tid = uuid.uuid4().hex
        if not source.startswith('magnet:?'):
            original = Path(source)
            if not original.is_file() or original.suffix.lower() != '.torrent':
                raise ValueError('Нужна magnet-ссылка или файл .torrent.')
            copied = self.data / (tid + '.torrent')
            shutil.copyfile(original, copied)
            source = str(copied)
        self._add({'id': tid, 'source': source, 'path': str(path), 'paused': False, 'autoAdd': bool(auto_add)})
        self.save()
        return {'ok': True}

    def action(self, tid, action):
        self.start()
        if tid not in self.handles:
            raise ValueError('Загрузка не найдена.')
        handle = self.handles[tid]
        if action == 'remove':
            self.session.remove_torrent(handle)  # Keep downloaded files.
            del self.handles[tid]
            del self.entries[tid]
        elif action in ('pause', 'resume'):
            paused = action == 'pause'
            self.entries[tid]['paused'] = paused
            if paused:
                handle.unset_flags(self.lt.torrent_flags.auto_managed)
                handle.pause()
            else:
                handle.set_flags(self.lt.torrent_flags.auto_managed)
                handle.resume()
        else:
            raise ValueError('Неизвестное действие загрузки.')
        self.save()
        return {'ok': True}

    def status(self):
        # Do not start listening on the network until the user opens Downloads.
        self.start()
        self.session.pop_alerts()
        rows = []
        for tid, handle in self.handles.items():
            status = handle.status()
            if status.has_metadata and tid not in self.validated:
                storage = handle.torrent_file().files()
                unsafe = any(Path(storage.file_path(i)).is_absolute() or '..' in Path(storage.file_path(i)).parts or storage.file_flags(i) & self.lt.file_storage.flag_symlink for i in range(storage.num_files()))
                if unsafe:
                    self.action(tid, 'pause')
                    self.error = 'Загрузка остановлена: торрент содержит ссылку или недопустимый путь.'
                else:
                    self.validated.add(tid)
                    handle.unset_flags(self.lt.torrent_flags.upload_mode)
            rows.append({'id': tid, 'name': status.name or 'Получение метаданных…', 'progress': round(status.progress * 100, 1), 'speed': status.download_rate, 'uploaded': status.total_upload, 'peers': status.num_peers, 'paused': self.entries[tid]['paused'], 'path': self.entries[tid]['path'], 'complete': status.is_seeding, 'autoAdd': self.entries[tid].get('autoAdd', True), 'error': status.errc.message() if status.errc.value() else '', 'queued': bool(status.paused and not self.entries[tid]['paused'])})
        return {'items': rows, 'errorMessage': self.error}

    def completed(self):
        if not self.session:
            return []
        result=[]
        for tid,handle in self.handles.items():
            status=handle.status()
            if status.is_seeding and tid in self.validated and self.entries[tid].get('autoAdd', True):
                files=handle.torrent_file().files()
                result.append({'id':tid,'name':status.name,'path':self.entries[tid]['path'],'files':[files.file_path(i) for i in range(files.num_files())]})
        return result

    def limits(self, download, upload):
        self.start()
        down, up = int(download), int(upload)
        if not 0 <= down <= 1000000 or not 0 <= up <= 1000000:
            raise ValueError('Скорость должна быть от 0 до 1000000 КиБ/с.')
        self.session.apply_settings({'download_rate_limit': down * 1024, 'upload_rate_limit': up * 1024})
        return {'ok': True}
