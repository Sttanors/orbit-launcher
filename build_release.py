#!/usr/bin/env python3
"""Build native release artifacts on the target OS. No personal data is bundled."""
from pathlib import Path
import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from launcher import VERSION
OUT = ROOT / 'release-dist'
WORK = ROOT / 'build/release'


def run(*args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def bundle(windows):
    name = 'Orbit' if windows else 'orbit'
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', name,
           '--distpath', str(WORK / 'dist'), '--workpath', str(WORK / 'pyinstaller'), '--specpath', str(WORK),
           '--add-data', f'{ROOT / "ui"}{os.pathsep}ui', '--hidden-import', 'PySide6.QtSvg',
           '--copy-metadata', 'PySide6', '--copy-metadata', 'PySide6_Essentials', '--copy-metadata', 'PySide6_Addons',
           '--copy-metadata', 'shiboken6', '--copy-metadata', 'psutil', '--collect-all', 'pygame', '--hidden-import', 'libtorrent',
           '--collect-data', 'certifi']
    if windows:
        cmd += ['--windowed']
    cmd += [str(ROOT / 'launcher.py')]
    run(*cmd)
    return WORK / 'dist' / name


def linux_packages(app):
    stage = WORK / 'payload'
    shutil.copytree(app, stage / 'opt/orbit', dirs_exist_ok=True)
    for folder in ('usr/bin', 'usr/share/applications', 'usr/share/icons/hicolor/scalable/apps'):
        (stage / folder).mkdir(parents=True, exist_ok=True)
    wrapper = stage / 'usr/bin/orbit'
    wrapper.write_text('#!/bin/sh\nexec /opt/orbit/orbit "$@"\n', encoding='utf-8')
    wrapper.chmod(0o755)
    desktop = ('[Desktop Entry]\nType=Application\nName=Orbit\nComment=Steam and custom game launcher\n'
               'Exec=orbit\nIcon=orbit\nTerminal=false\nCategories=Game;\nStartupWMClass=Orbit\n')
    (stage / 'usr/share/applications/orbit.desktop').write_text(desktop, encoding='utf-8')
    shutil.copyfile(ROOT / 'ui/icon.svg', stage / 'usr/share/icons/hicolor/scalable/apps/orbit.svg')
    size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
    deb = WORK / 'deb'
    shutil.copytree(stage, deb, dirs_exist_ok=True)
    (deb / 'DEBIAN').mkdir(exist_ok=True)
    (deb / 'DEBIAN/control').write_text(f'''Package: orbit-launcher
Version: {VERSION}
Section: games
Priority: optional
Architecture: amd64
Maintainer: Sttanors <Sttanors@users.noreply.github.com>
Installed-Size: {(size + 1023) // 1024}
Depends: libc6 (>= 2.35), libgl1, libegl1, libx11-6, libxcb1, libxkbcommon0, libnss3, libasound2 | libasound2t64, libdbus-1-3, libfontconfig1, libxrender1, libxext6, libxcomposite1, libxdamage1, libxrandr2, libxtst6, libxi6, libxkbcommon-x11-0, libxcb-cursor0
Recommends: xdotool
Homepage: https://github.com/Sttanors/orbit-launcher
Description: Console-style Steam and custom game launcher
 Orbit provides a controller-friendly local game library for Linux.
''', encoding='utf-8')
    run('dpkg-deb', '--root-owner-group', '-Zxz', '--build', deb, OUT / f'orbit-launcher_{VERSION}_amd64.deb')
    rpm = WORK / 'rpm'
    for folder in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
        (rpm / folder).mkdir(parents=True, exist_ok=True)
    spec = rpm / 'SPECS/orbit.spec'
    spec.write_text(f'''%global __os_install_post %{{nil}}
%global debug_package %{{nil}}
Name: orbit-launcher
Version: {VERSION}
Release: 1
Summary: Console-style Steam and custom game launcher
License: LicenseRef-Proprietary
URL: https://github.com/Sttanors/orbit-launcher
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.35, mesa-libGL, mesa-libEGL, libX11, libxcb, libxkbcommon, nss, alsa-lib, dbus-libs, fontconfig, libXrender, libXext, libXcomposite, libXdamage, libXrandr, libXtst, libXi, libxkbcommon-x11, xcb-util-cursor
Recommends: xdotool
%description
Orbit provides a controller-friendly local game library.
%prep
%build
%install
mkdir -p %{{buildroot}}
cp -a "{stage}/." %{{buildroot}}/
%files
/opt/orbit
/usr/bin/orbit
/usr/share/applications/orbit.desktop
/usr/share/icons/hicolor/scalable/apps/orbit.svg
''', encoding='utf-8')
    run('rpmbuild', '--define', f'_topdir {rpm}', '--define', '_build_id_links none', '-bb', spec)
    source = next((rpm / 'RPMS').rglob('*.rpm'))
    shutil.copyfile(source, OUT / f'orbit-launcher-{VERSION}-1.x86_64.rpm')
    arch = WORK / 'arch'
    shutil.copytree(stage, arch, dirs_exist_ok=True)
    dependencies = ['glibc', 'libglvnd', 'libx11', 'libxcb', 'libxkbcommon', 'nss', 'alsa-lib', 'dbus', 'fontconfig',
                    'libxrender', 'libxext', 'libxcomposite', 'libxdamage', 'libxrandr', 'libxtst', 'libxi', 'libxkbcommon-x11', 'xcb-util-cursor']
    metadata = (f'pkgname = orbit-launcher\npkgbase = orbit-launcher\npkgver = {VERSION}-1\n'
                f'pkgdesc = Console-style Steam and custom game launcher\nurl = https://github.com/Sttanors/orbit-launcher\n'
                f'builddate = {int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))}\npackager = Sttanors\nsize = {size}\n'
                'arch = x86_64\nlicense = LicenseRef-Proprietary\n' + ''.join(f'depend = {d}\n' for d in dependencies) +
                'optdepend = xdotool: minimize the Steam library during account switches\n')
    (arch / '.PKGINFO').write_text(metadata, encoding='utf-8')
    run('tar', '-I', 'zstd -12 -T0', '--owner=0', '--group=0', '-cf', OUT / f'orbit-launcher-{VERSION}-1-x86_64.pkg.tar.zst',
        '-C', arch, '.PKGINFO', 'opt', 'usr')
    # Verify native package metadata, not just archive extensions.
    run('dpkg-deb', '--info', OUT / f'orbit-launcher_{VERSION}_amd64.deb')
    run('rpm', '-qp', '--info', OUT / f'orbit-launcher-{VERSION}-1.x86_64.rpm')
    run('tar', '--zstd', '-xOf', OUT / f'orbit-launcher-{VERSION}-1-x86_64.pkg.tar.zst', '.PKGINFO')


def windows_installer(app):
    # An installer EXE avoids extracting the large QtWebEngine runtime on every launch.
    output = OUT / f'Orbit-{VERSION}-windows-x64-setup.exe'
    compiler = shutil.which('ISCC') or shutil.which('iscc')
    if not compiler:
        candidate = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Inno Setup 6/ISCC.exe'
        if candidate.exists():
            compiler = str(candidate)
    if not compiler:
        raise RuntimeError('Inno Setup 6 is required to build the Windows installer')
    script = WORK / 'orbit.iss'
    script.write_text(f'''[Setup]
AppId=OrbitLauncher
AppName=Orbit
AppVersion={VERSION}
AppPublisher=Sttanors
AppPublisherURL=https://github.com/Sttanors/orbit-launcher
DefaultDirName={{localappdata}}\\Programs\\Orbit
DefaultGroupName=Orbit
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={OUT}
OutputBaseFilename={output.stem}
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={{app}}\\Orbit.exe
WizardStyle=modern
[Files]
Source: "{app}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{{group}}\\Orbit"; Filename: "{{app}}\\Orbit.exe"
Name: "{{userdesktop}}\\Orbit"; Filename: "{{app}}\\Orbit.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{{app}}\\Orbit.exe"; Description: "Launch Orbit"; Flags: nowait postinstall skipifsilent
Filename: "{{app}}\\Orbit.exe"; Flags: nowait; Check: WizardSilent
''', encoding='utf-8-sig')
    run(compiler, script)
    if not output.exists():
        raise RuntimeError('Windows installer was not produced')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle-only', action='store_true')
    args = parser.parse_args()
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Release builds currently support x86_64 only')
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    app = bundle(sys.platform == 'win32')
    if args.bundle_only:
        return
    if sys.platform == 'win32':
        windows_installer(app)
    else:
        linux_packages(app)
    artifacts = sorted(p for p in OUT.iterdir() if p.is_file() and p.suffix != '.txt')
    checksum = OUT / ('SHA256SUMS-windows.txt' if sys.platform == 'win32' else 'SHA256SUMS-linux.txt')
    checksum.write_text(''.join(f'{hashlib.file_digest(p.open("rb"), "sha256").hexdigest()}  {p.name}\n' for p in artifacts), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
