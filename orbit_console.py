"""Opt-in desktop integration and owned game process tracking."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import psutil


def launch_command():
    return [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('launcher.py'))]


def autostart(enabled):
    command = launch_command()
    if sys.platform == 'win32':
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if enabled:
                winreg.SetValueEx(key, 'Orbit', 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, 'Orbit')
                except FileNotFoundError:
                    pass
    else:
        file = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'autostart/orbit.desktop'
        if enabled:
            file.parent.mkdir(parents=True, exist_ok=True)
            # Desktop Entry Exec quoting differs from shell quoting.
            escaped = ['"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"' for arg in command]
            file.write_text('[Desktop Entry]\nType=Application\nName=Orbit\nExec=' + ' '.join(escaped) + '\nTerminal=false\n', encoding='utf-8')
        else:
            file.unlink(missing_ok=True)


def power(action):
    if action not in ('suspend', 'poweroff'):
        raise ValueError('Неизвестное действие питания.')
    if sys.platform == 'win32':
        if action == 'poweroff':
            subprocess.Popen(['shutdown', '/s', '/t', '0'])
        else:
            import ctypes
            if not ctypes.windll.powrprof.SetSuspendState(False, False, False):
                raise OSError('Не удалось перевести Windows в спящий режим.')
    else:
        result = subprocess.run(['systemctl', action], capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise ValueError(result.stderr.strip() or 'Система отклонила действие питания.')


class GameSession:
    def __init__(self, game, process=None):
        self.game = dict(game)
        self.started = time.monotonic()
        self.seen = False
        self.processes = []
        if process:
            try:
                self.processes.append(psutil.Process(process.pid))
                self.seen = True
            except psutil.Error:
                pass

    def alive(self):
        if self.game['source'] == 'steam':
            user = psutil.Process().username()
            alive = False
            for proc in psutil.process_iter(['username']):
                try:
                    if proc.info['username'] == user:
                        env = proc.environ()
                        if env.get('SteamAppId') == self.game['appid'] or env.get('SteamGameId') == self.game['appid']:
                            self.processes.append(proc) if proc not in self.processes else None
                            alive = True
                except (psutil.Error, OSError):
                    pass
            if sys.platform == 'win32':
                import winreg
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Valve\\Steam\\Apps\\' + self.game['appid']) as key:
                        alive = bool(winreg.QueryValueEx(key, 'Running')[0])
                except OSError:
                    pass
        else:
            for proc in list(self.processes):
                try:
                    for child in proc.children(recursive=True):
                        if child not in self.processes:
                            self.processes.append(child)
                except psutil.Error:
                    pass
            alive = any(self._alive(p) for p in self.processes)
        self.seen |= alive
        return alive

    @staticmethod
    def _alive(proc):
        try:
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    def stop(self):
        # Only descendants / matching app IDs observed for this launch, with PID reuse protection.
        self.alive()
        for proc in reversed(self.processes):
            try:
                if self._alive(proc):
                    proc.terminate()
            except psutil.Error:
                pass

    def resume(self):
        pids = {p.pid for p in self.processes if self._alive(p)}
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            def visit(hwnd, _):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids and user32.IsWindowVisible(hwnd):
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    return False
                return True
            user32.EnumWindows(callback(visit), 0)
        else:
            import shutil
            if not shutil.which('xdotool'):
                raise ValueError('Для возврата в окно игры на X11 установи xdotool. На Wayland используй переключение окон системы.')
            for pid in pids:
                result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(pid)], capture_output=True, text=True, timeout=2)
                windows = result.stdout.split()
                if windows:
                    subprocess.run(['xdotool', 'windowactivate', windows[-1]], timeout=2, check=False)
                    return
            raise ValueError('Окно игры пока не найдено. Можно переключиться через Alt+Tab.')


class GuideButton:
    def __init__(self):
        self.ready = False
        self.controllers = {}
        self.error = ''

    def poll(self):
        try:
            os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
            os.environ.setdefault('SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS', '1')
            import pygame
            from pygame._sdl2 import controller
            if not self.ready:
                pygame.display.init()
                controller.init()
                self.ready = True
            pygame.event.pump()
            for index in range(controller.get_count()):
                if controller.is_controller(index):
                    if index not in self.controllers or not self.controllers[index].attached():
                        self.controllers[index] = controller.Controller(index)
            for event in pygame.event.get():
                if event.type == pygame.CONTROLLERBUTTONDOWN and event.button == pygame.CONTROLLER_BUTTON_GUIDE:
                    return True
        except (ImportError, RuntimeError, OSError) as error:
            self.error = str(error)
        return False
