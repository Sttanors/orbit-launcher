#!/usr/bin/env python3
"""Orbit — a local, offline-first game launcher for Linux and Windows."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
import uuid

import orbit_platform as platform
import orbit_services as services
import orbit_console as console
from concurrent.futures import ThreadPoolExecutor

VERSION = "0.2.2"

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
LEGACY_DATA = Path(__file__).resolve().parent / 'data'
DATA = Path(os.environ.get('ORBIT_DATA_DIR') or (LEGACY_DATA if not getattr(sys, 'frozen', False) and LEGACY_DATA.exists() else platform.user_data_directory()))


def parse_arguments(text):
    if '\0' in text:
        raise ValueError('Недопустимый символ в аргументах запуска.')
    return platform.split_windows_arguments(text) if platform.IS_WINDOWS else shlex.split(text)


def read_vdf(path):
    """Read Steam's text KeyValues (including escaped paths)."""
    tokens = re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', path.read_text(encoding='utf-8', errors='replace'))
    stack, result = [], {}
    current, key = result, None
    for value, brace in tokens:
        if brace == '{':
            child = {}
            current[key] = child
            stack.append(current)
            current, key = child, None
        elif brace == '}':
            current, key = stack.pop(), None
        else:
            value = value.replace('\\\\', '\\').replace('\\"', '"')
            if key is None:
                key = value
            else:
                current[key], key = value, None
    return result


def app_names(path):
    """Read names/types from Steam appinfo v29's indexed string table."""
    if not path.exists():
        return {}
    raw = path.read_bytes()
    if len(raw) < 16 or struct.unpack_from('<I', raw)[0] != 0x07564429:
        return {}
    offset = struct.unpack_from('<Q', raw, 8)[0]
    count = struct.unpack_from('<I', raw, offset)[0]
    strings = raw[offset + 4:].split(b'\0')[:count]
    try:
        keys = {key: b'\x01' + struct.pack('<I', strings.index(key.encode())) for key in ('name', 'type')}
    except ValueError:
        return {}
    names, pos = {}, 16
    while pos + 8 <= offset:
        appid, size = struct.unpack_from('<II', raw, pos)
        if not appid or size < 40 or pos + 8 + size > offset:
            break
        chunk = raw[pos + 8:pos + 8 + size]
        meta = {}
        for key, token in keys.items():
            at = chunk.find(token)
            if at >= 0:
                meta[key] = chunk[at + 5:].split(b'\0', 1)[0].decode('utf-8', errors='replace')
        if meta.get('name'):
            names[str(appid)] = meta
        pos += 8 + size
    return names


def steam_roots():
    if platform.IS_WINDOWS:
        return platform.windows_steam_roots()
    paths = [Path.home() / x for x in ('.local/share/Steam', '.steam/steam', '.var/app/com.valvesoftware.Steam/data/Steam')]
    return list(dict.fromkeys(p.resolve() for p in paths if p.exists()))



def steam_command(root=None):
    if platform.IS_WINDOWS:
        roots = ([Path(root)] if root else []) + steam_roots()
        for path in roots:
            exe = path / 'steam.exe'
            if exe.is_file():
                return [str(exe)]
        raise ValueError('Steam не найден. Установите Steam и войдите в аккаунт.')
    if root and '/.var/app/com.valvesoftware.Steam/' in str(root):
        if shutil.which('flatpak'):
            return ['flatpak', 'run', 'com.valvesoftware.Steam']
        raise ValueError('Flatpak Steam не найден.')
    if shutil.which('steam'):
        return ['steam']
    if shutil.which('flatpak'):
        return ['flatpak', 'run', 'com.valvesoftware.Steam']
    raise ValueError('Steam не найден. Установите Steam и войдите в аккаунт.')


def start_steam(root, arguments, skip_shader_precache=False):
    command = steam_command(root)
    environment = os.environ.copy()
    if skip_shader_precache:
        environment['STEAM_ENABLE_SHADER_CACHE_MANAGEMENT'] = '0'
        if command[:2] == ['flatpak', 'run']:
            command.insert(2, '--env=STEAM_ENABLE_SHADER_CACHE_MANAGEMENT=0')
    return subprocess.Popen(command + arguments, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def steam_accounts():
    accounts = {}
    for root in steam_roots():
        path = root / 'config/loginusers.vdf'
        if not path.exists():
            continue
        for sid, user in read_vdf(path).get('users', {}).items():
            if sid.isdigit() and isinstance(user, dict) and user.get('AccountName'):
                accounts[sid] = {'id': sid, 'login': user['AccountName'], 'name': user.get('PersonaName') or user['AccountName'], 'root': str(root)}
    return list(accounts.values())


def steam_processes():
    """Read only this user's Steam processes; never signal unrelated processes."""
    if platform.IS_WINDOWS:
        return platform.windows_steam_processes()
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            command = (proc / 'cmdline').read_bytes().split(b'\0')
            executable = Path(os.fsdecode(command[0])).name
            if executable in ('steam', 'steamwebhelper'):
                found.append((int(proc.name), [os.fsdecode(x) for x in command]))
        except (OSError, IndexError):
            continue
    return found


def minimize_steam_library():
    """Minimize authenticated Steam's main X11/Xwayland window, never games/login dialogs."""
    if platform.IS_WINDOWS:
        return platform.windows_minimize_steam({pid for pid, _ in steam_processes()})
    if not shutil.which('xdotool') or not os.environ.get('DISPLAY'):
        return 0
    owned = {pid for pid, _ in steam_processes()}
    if not owned:
        return 0
    def xdo(*args):
        return subprocess.run(['xdotool', *args], capture_output=True, text=True, timeout=1, check=False)
    count = 0
    try:
        result = xdo('search', '--onlyvisible', '--class', '^(steam|steamwebhelper)$')
        for wid in result.stdout.split()[:24]:
            if not wid.isdigit():
                continue
            pid = xdo('getwindowpid', wid).stdout.strip()
            title = xdo('getwindowname', wid).stdout.strip()
            if pid.isdigit() and int(pid) in owned and title == 'Steam':
                if xdo('windowminimize', wid).returncode == 0:
                    count += 1
    except (OSError, subprocess.TimeoutExpired):
        pass
    return count


def account_from_connection_log(text, started):
    """Use logon events from this Steam session, never stale events from yesterday."""
    for line in reversed(text.splitlines()):
        stamp = re.match(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]', line)
        if not stamp:
            continue
        if datetime.strptime(stamp[1], '%Y-%m-%d %H:%M:%S').timestamp() < started - 5:
            return ''
        if any(event in line for event in ('Logging Off', 'Logged Off', 'LogOff', 'Logoff')):
            return ''
        if '[Logged On,' in line and 'processing complete' in line:
            match = re.search(r'\[U:1:(\d+)\]', line)
            if match:
                return str(76561197960265728 + int(match[1]))
    return ''


def active_steam_account():
    if platform.IS_WINDOWS:
        return platform.windows_active_account() if steam_processes() else ''
    processes = steam_processes()
    for _, args in processes:
        for arg in args:
            if re.match(r'^--?steamid=', arg):
                sid = arg.partition('=')[2]
                if sid.isdigit() and int(sid) > 0:
                    return str(int(sid) if int(sid) > 76561197960265728 else 76561197960265728 + int(sid))
    # Newer clients can leave steamwebhelper's ID at zero even while logged in.
    try:
        boot = int(re.search(r'^btime (\d+)', Path('/proc/stat').read_text(), re.M)[1])
        starts = []
        for pid, args in processes:
            if Path(args[0]).name == 'steam':
                fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
                starts.append(boot + int(fields[19]) / os.sysconf('SC_CLK_TCK'))
        if not starts:
            return ''
        for root in steam_roots():
            path = root / 'logs/connection_log.txt'
            if path.exists():
                with path.open('rb') as stream:
                    stream.seek(max(0, path.stat().st_size - 131072))
                    sid = account_from_connection_log(stream.read().decode(errors='replace'), min(starts))
                    if sid:
                        return sid
    except (OSError, ValueError, TypeError, IndexError):
        pass
    return ''


def running_steam_games():
    if platform.IS_WINDOWS:
        return platform.windows_running_games()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            env = (proc / 'environ').read_bytes().split(b'\0')
            if any(re.fullmatch(rb'Steam(?:App|Game)Id=[1-9][0-9]*', item) for item in env):
                return True
        except OSError:
            continue
    return False


def artwork(root, appid, kind):
    cache = root / 'appcache/librarycache'
    names = ['library_hero.jpg', 'library_hero.png'] if kind == 'hero' else ['library_capsule.jpg', 'library_600x900.jpg', 'header.jpg']
    for name in names:
        found = list((cache / appid).glob(f'*/{name}')) + list((cache / appid).glob(name)) + list(cache.glob(f'{appid}_{name}'))
        if found:
            return found[0].as_uri()
    return ''


def scan_steam():
    games = {}
    for root in steam_roots():
        names = app_names(root / 'appcache/appinfo.vdf')
        libraries = {str(root): {}}
        folders = root / 'steamapps/libraryfolders.vdf'
        if folders.exists():
            for entry in read_vdf(folders).get('libraryfolders', {}).values():
                if isinstance(entry, dict) and entry.get('path'):
                    libraries[entry['path']] = entry.get('apps', {})
        for folder, registered in libraries.items():
            steamapps = Path(folder) / 'steamapps'
            manifests = {}
            if steamapps.exists():
                for manifest in steamapps.glob('appmanifest_*.acf'):
                    try:
                        state = read_vdf(manifest).get('AppState', {})
                        manifests[state['appid']] = state
                    except (OSError, ValueError, KeyError, IndexError):
                        continue
            for appid in set(registered) | set(manifests):
                state, meta = manifests.get(appid, {}), names.get(appid, {})
                if appid == '228980' or meta.get('type', '').lower() in ('tool', 'dlc', 'demo', 'config', 'application', 'video', 'music'):
                    continue
                available = bool(state) and bool(int(state.get('StateFlags', '0')) & 4) and (steamapps / 'common' / state.get('installdir', '__missing__')).is_dir()
                games[appid] = {'id': 'steam-' + appid, 'appid': appid, 'name': state.get('name') or meta.get('name') or f'Steam · {appid}', 'source': 'steam', 'installed': available, 'cover': artwork(root, appid, 'cover'), 'hero': artwork(root, appid, 'hero'), 'library': folder, 'steamRoot': str(root), 'lastOwner': state.get('LastOwner', '')}
    return list(games.values())


class Library:
    def __init__(self, data=DATA):
        self.data = Path(data)
        self.path = self.data / 'library.json'
        self.state = {'custom': [], 'favorites': [], 'recent': {}, 'steamAccounts': {}, 'skipShaderPrecache': False, 'saves': {}, 'consoleMode': False, 'autostart': False, 'torrentLimits': [0, 0]}
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            self.state.update(saved)
        self.games = []
        self.last_process = None

    def save(self):
        self.data.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def refresh(self):
        self.games = scan_steam() + [{**g, 'installed': Path(g['path']).is_file()} for g in self.state['custom']]
        accounts = {a['id'] for a in steam_accounts()}
        for game in self.games:
            if game['source'] == 'steam':
                preferred = self.state['steamAccounts'].get(game['id'], game.get('lastOwner', ''))
                game['accountId'] = preferred if preferred in accounts else ''
        return [{**g, 'favorite': g['id'] in self.state['favorites'], 'lastPlayed': self.state['recent'].get(g['id'], 0)} for g in self.games]

    def game(self, game_id):
        return next((g for g in self.games if g['id'] == game_id), None)

    def save_custom(self, p, game_id=None):
        existing = next((g for g in self.state['custom'] if g['id'] == game_id), None)
        if game_id and not existing:
            raise ValueError('Добавленная игра не найдена.')
        path = Path(p['path']).expanduser().resolve()
        name = p.get('name', '').strip()
        if not path.is_file() or not name:
            raise ValueError('Укажите название и существующий файл игры.')
        parse_arguments(p.get('arguments', ''))
        if p.get('runner', 'native') not in ('native', 'proton'):
            raise ValueError('Неизвестный способ запуска.')
        if platform.IS_WINDOWS and path.suffix.lower() not in ('.exe', '.com'):
            raise ValueError('Для Windows выбери исполняемый файл .exe или .com.')
        cwd = Path(p.get('cwd') or path.parent).expanduser().resolve()
        if not cwd.is_dir():
            raise ValueError('Рабочая папка не найдена.')
        gid = game_id or 'local-' + uuid.uuid4().hex
        cover = existing.get('cover', '') if existing else ''
        if p.get('clearCover'):
            cover = ''
        elif p.get('cover'):
            source = Path(p['cover'])
            if source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('Выберите изображение PNG, JPG или WebP.')
            destination = self.data / 'covers' / (gid + '-' + uuid.uuid4().hex[:8] + source.suffix.lower())
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            cover = destination.as_uri()
        game = {'id': gid, 'name': name, 'path': str(path), 'arguments': p.get('arguments', ''), 'cwd': str(cwd), 'source': 'local', 'cover': cover, 'hero': cover, 'runner': p.get('runner', 'native'), 'proton': p.get('proton', '')}
        if existing:
            existing.update(game)
        else:
            self.state['custom'].append(game)
        self.save()
        return gid

    def set_account(self, game_id, account_id):
        game = self.game(game_id)
        if not game or game['source'] != 'steam':
            raise ValueError('Игра Steam не найдена.')
        if account_id and not any(a['id'] == account_id for a in steam_accounts()):
            raise ValueError('Этот аккаунт больше не сохранён в Steam.')
        self.state['steamAccounts'][game_id] = account_id
        game['accountId'] = account_id
        self.save()

    def steam_target(self, game):
        preferred = self.state['steamAccounts'].get(game['id'], game.get('accountId', ''))
        return next((a for a in steam_accounts() if a['id'] == preferred), None)

    def launch(self, game_id):
        game = self.game(game_id)
        if not game:
            raise ValueError('Игра больше не найдена. Обновите библиотеку.')
        if game['source'] == 'steam':
            target = self.steam_target(game)
            if target and target['id'] != active_steam_account():
                return {'needsAccountSwitch': True, 'account': target, 'gameId': game_id}
            start_steam(game.get('steamRoot'), ['-silent', '-applaunch', str(int(game['appid']))], self.state['skipShaderPrecache'])
        else:
            path = Path(game['path'])
            if not path.is_file():
                raise ValueError('Файл игры не найден. Возможно, диск отключён.')
            if platform.IS_WINDOWS and path.suffix.lower() not in ('.exe', '.com'):
                raise ValueError('Для Windows выбери файл .exe или .com.')
            command, environment = services.game_command(game, self.data, steam_roots(), platform.IS_WINDOWS)
            self.last_process = subprocess.Popen([*command, *parse_arguments(game.get('arguments', ''))], env=environment, cwd=str(Path(game.get('cwd') or path.parent)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.state['recent'][game_id] = time.time()
        self.save()
        return {'ok': True}


def create_bridge(window, library):
    from PySide6.QtCore import QObject, Slot, Signal, QTimer, Qt
    from PySide6.QtWidgets import QApplication, QFileDialog

    class Bridge(QObject):
        launchFinished = Signal(str)
        launchProgress = Signal(str)
        serviceFinished = Signal(str)
        sessionChanged = Signal(str)

        def __init__(self):
            super().__init__()
            self.pending = None
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='orbit-services')
            self.jobs = {}
            self.saves = services.Saves(library.data)
            self.updater = services.Updater(library.data, VERSION)
            self.torrents = services.Torrents(library.data)
            self.sessions = {}
            self.save_queue = []
            self.guide = console.GuideButton()
            self.last_session_poll = 0
            self.service_timer = QTimer(self)
            self.service_timer.setInterval(250)
            self.service_timer.timeout.connect(self.poll_services)
            self.service_timer.start()
            if (library.data / 'torrents/queue.json').exists():
                try:
                    self.torrents.start()
                    self.torrents.limits(*library.state['torrentLimits'])
                except (ImportError, OSError, RuntimeError, ValueError) as error:
                    self.torrents.error = str(error)
            self.presentation = None
            self.timer = QTimer(self)
            self.timer.setInterval(500)
            self.timer.timeout.connect(self.poll_switch)

        def job(self, kind, function, callback=None):
            if self.jobs:
                raise ValueError('Дождись завершения текущей фоновой операции.')
            jid = uuid.uuid4().hex
            self.jobs[jid] = (kind, self.executor.submit(function), callback)
            return {'job': jid}

        def launch_game(self, gid):
            game = library.game(gid)
            if not game:
                raise ValueError('Игра не найдена.')
            if gid in self.sessions:
                raise ValueError('Игра уже запущена. Открой меню текущей игры.')
            target = library.steam_target(game) if game['source'] == 'steam' else None
            if target and target['id'] != active_steam_account():
                return {'needsAccountSwitch': True, 'account': target, 'gameId': gid}
            profile = library.state['saves'].get(gid)
            def start():
                library.last_process = None
                result = library.launch(gid)
                if result.get('ok'):
                    self.sessions[gid] = console.GameSession(game, library.last_process)
                    self.sessionChanged.emit(json.dumps({'message': 'Игра запущена: ' + game.get('name', game['id'])}))
                return result
            if profile:
                self.job('beforeLaunch', lambda: self.saves.sync(gid, profile), lambda _: self.launchFinished.emit(json.dumps(start())))
                return {'preparing': True}
            return start()

        def poll_services(self):
            for jid, (kind, future, callback) in list(self.jobs.items()):
                if not future.done():
                    continue
                del self.jobs[jid]
                try:
                    result = future.result()
                    if callback:
                        callback(result)
                    self.serviceFinished.emit(json.dumps({'job': jid, 'kind': kind, 'result': result}, ensure_ascii=False))
                except Exception as error:
                    result = {'error': str(error), 'conflict': isinstance(error, services.SaveConflict)}
                    self.serviceFinished.emit(json.dumps({'job': jid, 'kind': kind, **result}, ensure_ascii=False))
                    if kind == 'beforeLaunch':
                        self.launchFinished.emit(json.dumps(result, ensure_ascii=False))
            if self.save_queue and not self.jobs:
                gid, profile = self.save_queue.pop(0)
                self.job('afterGame', lambda g=gid, p=profile: self.saves.sync(g, p))
            if library.state['consoleMode'] and self.guide.poll():
                window.showFullScreen()
                window.raise_()
                window.activateWindow()
                window.centralWidget().page().runJavaScript("window.orbitRunningMenu?.()")
            if time.monotonic() - self.last_session_poll < 3:
                return
            self.last_session_poll = time.monotonic()
            if self.torrents.session:
                try:
                    self.torrents.status()
                except (OSError, RuntimeError, ValueError) as error:
                    self.torrents.error = str(error)
            for gid, session in list(self.sessions.items()):
                if not session.alive() and session.seen:
                    del self.sessions[gid]
                    profile = library.state['saves'].get(gid)
                    if profile:
                        self.save_queue.append((gid, dict(profile)))
                    self.sessionChanged.emit(json.dumps({'message': 'Игра завершена: ' + session.game.get('name', game['id'])}))
                elif not session.seen and time.monotonic() - session.started > 120:
                    del self.sessions[gid]
                    self.sessionChanged.emit(json.dumps({'message': 'Запуск не подтверждён: ' + session.game.get('name', game['id'])}))

        def feature_request(self, action, p):
            if action == 'features':
                return {'protons': [] if platform.IS_WINDOWS else services.proton_versions(steam_roots()), 'consoleMode': library.state['consoleMode'], 'autostart': library.state['autostart'], 'saves': library.state['saves'], 'version': VERSION, 'limits': library.state['torrentLimits'], 'sessions': [{'id': gid, 'name': s.game['name']} for gid, s in self.sessions.items()], 'guideError': self.guide.error}
            if action == 'saveProfile':
                gid = p['id']
                if gid in self.sessions or self.jobs:
                    raise ValueError('Закрой игру и дождись фоновых операций перед изменением синхронизации.')
                if not library.game(gid):
                    raise ValueError('Игра не найдена.')
                if p.get('enabled'):
                    profile = {k: p.get(k, '').strip() for k in ('local', 'cloud', 'key')}
                    self.saves.locations(profile)
                    if library.state['saves'].get(gid) != profile:
                        (library.data / 'save-baselines' / (gid + '.json')).unlink(missing_ok=True)
                    library.state['saves'][gid] = profile
                else:
                    library.state['saves'].pop(gid, None)
                library.save()
                return {'ok': True}
            if action in ('syncSaves', 'saveHistory'):
                gid = p['id']
                if gid in self.sessions:
                    raise ValueError('Сначала закрой игру, чтобы не менять сохранения во время игры.')
                profile = dict(library.state['saves'].get(gid, {}))
                return self.job(action, lambda: {'history': self.saves.history(profile)} if action == 'saveHistory' else self.saves.sync(gid, profile, p.get('choice', ''), p.get('snapshot', '')))
            if action in ('checkUpdate', 'downloadUpdate'):
                return self.job(action, self.updater.check if action == 'checkUpdate' else self.updater.download)
            if action == 'installUpdate':
                if self.sessions or self.pending or self.jobs:
                    raise ValueError('Закрой игры и дождись фоновых операций перед обновлением.')
                result = self.updater.install()
                QTimer.singleShot(800, QApplication.instance().quit)
                return result
            if action == 'torrentStatus':
                return self.torrents.status()
            if action == 'torrentAdd':
                result = self.torrents.add(p['source'], p['path'])
                self.torrents.limits(*library.state['torrentLimits'])
                return result
            if action == 'torrentAction':
                return self.torrents.action(p['id'], p['action'])
            if action == 'torrentLimits':
                result = self.torrents.limits(p['download'], p['upload'])
                library.state['torrentLimits'] = [int(p['download']), int(p['upload'])]
                library.save()
                return result
            if action == 'chooseTorrent':
                return {'path': QFileDialog.getOpenFileName(window, 'Выбрать торрент', str(Path.home()), 'Torrent (*.torrent)')[0]}
            if action == 'openFolder':
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                path = Path(p['path']).expanduser().resolve()
                if not path.is_dir():
                    raise ValueError('Папка не найдена.')
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                return {'ok': True}
            if action == 'consoleSettings':
                if 'autostart' in p:
                    console.autostart(bool(p['autostart']))
                    library.state['autostart'] = bool(p['autostart'])
                if 'enabled' in p:
                    library.state['consoleMode'] = bool(p['enabled'])
                library.save()
                return {'ok': True}
            if action in ('stopGame', 'resumeGame'):
                session = self.sessions.get(p['id'])
                if not session:
                    raise ValueError('Запущенная игра не найдена.')
                session.stop() if action == 'stopGame' else session.resume()
                return {'ok': True}
            if action == 'power':
                if self.sessions or self.jobs:
                    raise ValueError('Сначала закрой игры и дождись сохранения данных.')
                console.power(p['action'])
                return {'ok': True}
            raise ValueError('Неизвестное действие')

        def protect_switch(self):
            self.presentation = {'fullscreen': window.isFullScreen(), 'geometry': window.saveGeometry()}
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            window.showFullScreen()
            window.raise_()
            window.activateWindow()

        def reveal_switch(self):
            if self.presentation is None:
                return
            previous = self.presentation
            self.presentation = None
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            if previous['fullscreen']:
                window.showFullScreen()
            else:
                window.restoreGeometry(previous['geometry'])
                window.showNormal()

        def poll_switch(self):
            try:
                if self.pending['phase'] == 'login':
                    active = active_steam_account()
                    if active and (not self.pending['account']['id'] or active == self.pending['account']['id']):
                        # Keep Orbit above late-created library windows until login settles.
                        minimize_steam_library()
                        if not self.pending.get('readySince'):
                            self.pending['readySince'] = time.monotonic()
                            return
                        if time.monotonic() - self.pending['readySince'] < 1.5:
                            return
                        self.reveal_switch()
                        result = {'ok': True, 'settingsApplied': True} if self.pending.get('restartOnly') else self.launch_game(self.pending['gameId'])
                        if not result.get('ok') and not result.get('preparing'):
                            raise ValueError('Аккаунт игры изменился. Проверь параметры и повтори запуск.')
                        self.timer.stop()
                        self.pending = None
                        self.launchFinished.emit(json.dumps(result, ensure_ascii=False))
                    elif time.monotonic() > self.pending['deadline']:
                        raise ValueError('Вход в выбранный аккаунт не подтверждён за 3 минуты. Проверь Steam и Steam Guard, затем повтори запуск. Игра не запускалась.')
                    return
                pids = {pid for pid, _ in steam_processes()}
                if self.pending['pids'] & pids:
                    if time.monotonic() > self.pending['deadline']:
                        raise ValueError('Steam не завершился за 45 секунд. Закрой его вручную и повтори запуск. Принудительное завершение не выполнялось.')
                    return
                if not self.pending.get('quietSince'):
                    self.pending['quietSince'] = time.monotonic()
                    return
                if time.monotonic() - self.pending['quietSince'] < 1.5:
                    return
                account = self.pending['account']
                arguments = ['-silent'] if self.pending.get('restartOnly') else ['-silent', '-login', account['login']]
                start_steam(account['root'], arguments, library.state['skipShaderPrecache'])
                self.pending['phase'] = 'login'
                self.pending['deadline'] = time.monotonic() + 180
                self.launchProgress.emit('Жду входа в выбранный аккаунт. При необходимости открой Steam и подтверди вход / Steam Guard.')
            except (OSError, ValueError, KeyError) as error:
                self.timer.stop()
                self.pending = None
                self.reveal_switch()
                self.launchFinished.emit(json.dumps({'error': str(error)}, ensure_ascii=False))

        @Slot(str, str, result=str)
        def request(self, action, payload):
            try:
                p = json.loads(payload or '{}')
                if self.pending and action in ('setAccount', 'remove', 'edit') and p.get('id') == self.pending['gameId']:
                    raise ValueError('Дождись переключения Steam, прежде чем менять параметры этой игры.')
                if action == 'library':
                    result = {'games': library.refresh(), 'accounts': steam_accounts(), 'activeAccount': active_steam_account(), 'skipShaderPrecache': library.state['skipShaderPrecache'], 'platform': 'windows' if platform.IS_WINDOWS else 'linux', 'version': VERSION}
                elif action == 'launch':
                    if self.pending:
                        raise ValueError('Сначала дождись переключения аккаунта Steam.')
                    result = self.launch_game(p['id'])
                elif action == 'setShaderSkip':
                    if self.pending:
                        raise ValueError('Дождись завершения операции со Steam.')
                    if not isinstance(p.get('enabled'), bool):
                        raise ValueError('Некорректное значение настройки.')
                    library.state['skipShaderPrecache'] = p['enabled']
                    library.save()
                    result = {'ok': True, 'skipShaderPrecache': p['enabled']}
                elif action == 'restartSteam':
                    if self.pending:
                        raise ValueError('Операция со Steam уже выполняется.')
                    if running_steam_games():
                        raise ValueError('Сначала закрой игру Steam. Настройка сохранена, её можно применить позже.')
                    roots = steam_roots()
                    if not roots:
                        raise ValueError('Установка Steam не найдена.')
                    active = active_steam_account()
                    account = next((a for a in steam_accounts() if a['id'] == active), {'id': active, 'root': str(roots[0]), 'login': ''})
                    pids = {pid for pid, _ in steam_processes()}
                    if pids:
                        subprocess.Popen(steam_command(account['root']) + ['-shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.pending = {'gameId': None, 'account': account, 'restartOnly': True, 'phase': 'stopping', 'pids': pids, 'deadline': time.monotonic() + 45}
                    self.protect_switch()
                    self.timer.start()
                    result = {'switching': True}
                elif action == 'switchAndLaunch':
                    if self.pending:
                        raise ValueError('Аккаунт уже переключается.')
                    game = library.game(p['id'])
                    if not game or game['source'] != 'steam' or not library.steam_target(game):
                        raise ValueError('Выбери сохранённый аккаунт в параметрах игры.')
                    if running_steam_games():
                        raise ValueError('Сначала закрой запущенную игру Steam. Переключение аккаунта остановило бы её.')
                    pids = {pid for pid, _ in steam_processes()}
                    if pids:
                        subprocess.Popen(steam_command(game.get('steamRoot')) + ['-shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.pending = {'gameId': p['id'], 'account': library.steam_target(game), 'phase': 'stopping', 'pids': pids, 'deadline': time.monotonic() + 45}
                    self.protect_switch()
                    self.timer.start()
                    result = {'switching': True}
                elif action == 'cancelSwitch':
                    self.timer.stop()
                    self.pending = None
                    self.reveal_switch()
                    result = {'ok': True}
                elif action == 'showSteam':
                    self.reveal_switch()
                    start_steam(None, ['steam://open/main'], library.state['skipShaderPrecache'])
                    result = {'ok': True}
                elif action == 'setAccount':
                    library.set_account(p['id'], p.get('accountId', ''))
                    result = {'games': library.refresh()}
                elif action == 'chooseDirectory':
                    result = {'path': QFileDialog.getExistingDirectory(window, 'Рабочая папка игры', str(Path.home()))}
                elif action == 'favorite':
                    if not library.game(p['id']):
                        raise ValueError('Игра не найдена')
                    favorites = library.state['favorites']
                    favorites.remove(p['id']) if p['id'] in favorites else favorites.append(p['id'])
                    library.save()
                    result = {'ok': True}
                elif action == 'chooseExecutable':
                    path, _ = QFileDialog.getOpenFileName(window, 'Выбрать игру', str(Path.home()), 'Приложения (*.exe *.com)' if platform.IS_WINDOWS else 'Все файлы (*)')
                    result = {'path': path, 'name': Path(path).stem if path else ''}
                elif action == 'chooseCover':
                    path, _ = QFileDialog.getOpenFileName(window, 'Выбрать обложку', str(Path.home()), 'Изображения (*.png *.jpg *.jpeg *.webp)')
                    result = {'path': path}
                elif action in ('add', 'edit'):
                    gid = library.save_custom(p, p.get('id') if action == 'edit' else None)
                    result = {'games': library.refresh(), 'id': gid}
                elif action == 'remove':
                    library.state['custom'] = [g for g in library.state['custom'] if g['id'] != p['id']]
                    library.state['favorites'] = [i for i in library.state['favorites'] if i != p['id']]
                    library.state['recent'].pop(p['id'], None)
                    library.save()
                    result = {'games': library.refresh()}
                elif action == 'fullscreen':
                    window.showNormal() if window.isFullScreen() else window.showFullScreen()
                    result = {'ok': True}
                elif action == 'minimize':
                    self.reveal_switch()
                    window.showMinimized()
                    result = {'ok': True}
                elif action == 'quit':
                    QApplication.instance().quit()
                    result = {'ok': True}
                else:
                    result = self.feature_request(action, p)
                return json.dumps(result, ensure_ascii=False)
            except (OSError, ValueError, KeyError, RuntimeError, ImportError) as error:
                return json.dumps({'error': str(error)}, ensure_ascii=False)

    return Bridge()


def run():
    from PySide6.QtCore import QUrl, QTimer
    from PySide6.QtGui import QShortcut, QKeySequence
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebChannel import QWebChannel

    parser = argparse.ArgumentParser(description='Orbit game launcher')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--windowed', action='store_true')
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--apply-steam-settings', action='store_true', help='Restart Steam to apply the saved shader setting')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Orbit')
    window = QMainWindow()
    window.setWindowTitle('Orbit · Твоя игровая вселенная')
    from PySide6.QtGui import QIcon
    window.setWindowIcon(QIcon(str(ROOT / 'ui/icon.svg')))
    window.resize(1440, 920)
    view = QWebEngineView()
    window.setCentralWidget(view)
    library = Library()

    bridge = create_bridge(window, library)
    channel = QWebChannel()
    channel.registerObject('bridge', bridge)
    view.page().setWebChannel(channel)
    url = QUrl.fromLocalFile(str(ROOT / 'ui/index.html'))
    if args.apply_steam_settings:
        url.setQuery('applySteamSettings=1')
    view.setUrl(url)
    fullscreen = QShortcut(QKeySequence('F11'), window)
    fullscreen.activated.connect(lambda: window.showNormal() if window.isFullScreen() else window.showFullScreen())
    quit_key = QShortcut(QKeySequence('Ctrl+Q'), window)
    quit_key.activated.connect(app.quit)
    window.showNormal() if args.windowed else window.showFullScreen()
    if args.screenshot:
        def capture():
            view.grab().save(str(args.screenshot))
            app.quit()
        QTimer.singleShot(5000, capture)
    sys.exit(app.exec())


if __name__ == '__main__':
    run()
