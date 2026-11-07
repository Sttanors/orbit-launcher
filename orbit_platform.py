"""Small platform adapters used by the launcher and its release builds."""
from __future__ import annotations
import ctypes
import getpass
import os
from pathlib import Path
import sys

IS_WINDOWS = sys.platform == 'win32'


def user_data_directory(windows=None):
    windows = IS_WINDOWS if windows is None else windows
    if windows:
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Orbit'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'orbit'


def windows_steam_roots():
    paths = []
    try:
        import winreg
        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    paths.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(variable):
            paths.append(Path(os.environ[variable]) / 'Steam')
    return list(dict.fromkeys(p.resolve() for p in paths if p.is_dir()))


def windows_steam_processes():
    import psutil
    user = psutil.Process().username()
    found = []
    for proc in psutil.process_iter(['name', 'username', 'cmdline']):
        try:
            if proc.info['username'] == user and (proc.info['name'] or '').lower() in ('steam.exe', 'steamwebhelper.exe'):
                found.append((proc.pid, proc.info['cmdline'] or [proc.info['name']]))
        except (psutil.Error, OSError):
            pass
    return found


def windows_active_account():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\ActiveProcess') as handle:
            account = int(winreg.QueryValueEx(handle, 'ActiveUser')[0])
        return str(76561197960265728 + account) if account else ''
    except (OSError, ImportError, ValueError):
        return ''


def windows_running_games():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\Apps') as apps:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(apps, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(apps, name) as app:
                        if winreg.QueryValueEx(app, 'Running')[0]:
                            return True
                except OSError:
                    pass
    except (OSError, ImportError):
        pass
    return False


def windows_minimize_steam(pids):
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    count = 0
    def visit(hwnd, _):
        nonlocal count
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value == 'Steam':
                user32.ShowWindowAsync(hwnd, 6)
                count += 1
        return True
    user32.EnumWindows(callback_type(visit), 0)
    return count


def split_windows_arguments(text):
    """Use Windows' own command line parser; preserve spaces and literal backslashes."""
    if '\0' in text:
        raise ValueError('Недопустимый символ в аргументах запуска.')
    from ctypes import wintypes
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW('orbit ' + text, ctypes.byref(count))
    if not argv:
        raise OSError(ctypes.get_last_error(), 'Не удалось разобрать аргументы запуска')
    try:
        return [argv[i] for i in range(1, count.value)]
    finally:
        kernel32.LocalFree(argv)
