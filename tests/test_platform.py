import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher
import orbit_platform


class PlatformTests(unittest.TestCase):
    def test_windows_user_data_is_writable_user_folder(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': str(Path.home() / 'LocalAppData')}):
            self.assertEqual(orbit_platform.user_data_directory(True), Path.home() / 'LocalAppData/Orbit')

    def test_linux_user_data_uses_xdg(self):
        with patch.dict(os.environ, {'XDG_DATA_HOME': '/tmp/xdg'}):
            self.assertEqual(orbit_platform.user_data_directory(False), Path('/tmp/xdg/orbit'))

    def test_windows_steam_executable_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'Steam with spaces'
            root.mkdir()
            (root / 'steam.exe').write_bytes(b'test')
            with patch.object(orbit_platform, 'IS_WINDOWS', True):
                self.assertEqual(launcher.steam_command(root), [str(root / 'steam.exe')])

    def test_windows_platform_process_and_account_adapters(self):
        with patch.object(orbit_platform, 'IS_WINDOWS', True), patch.object(orbit_platform, 'windows_steam_processes', return_value=[(42,['steam.exe'])]), patch.object(orbit_platform, 'windows_active_account', return_value='account'):
            self.assertEqual(launcher.steam_processes(),[(42,['steam.exe'])])
            self.assertEqual(launcher.active_steam_account(),'account')

    def test_windows_native_game_does_not_need_unix_executable_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'Игра с пробелами.exe'
            file.write_bytes(b'test')
            library = launcher.Library(Path(directory) / 'data')
            library.games = [{'id':'local-test','source':'local','path':str(file),'arguments':'--fullscreen'}]
            with patch.object(orbit_platform, 'IS_WINDOWS', True), patch.object(orbit_platform, 'split_windows_arguments', return_value=['--fullscreen']), patch('launcher.os.access', return_value=False), patch('launcher.subprocess.Popen') as spawn:
                library.launch('local-test')
            self.assertEqual(spawn.call_args.args[0], [str(file),'--fullscreen'])

    def test_windows_rejects_scripts_instead_of_invoking_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'game.cmd'
            file.write_text('echo test',encoding='utf-8')
            library = launcher.Library(Path(directory)/'data')
            with patch.object(orbit_platform, 'IS_WINDOWS', True), patch.object(orbit_platform,'split_windows_arguments',return_value=[]):
                with self.assertRaisesRegex(ValueError, '.exe'):
                    library.save_custom({'name':'Game','path':str(file)})

    def test_unicode_library_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/('Игра.exe' if orbit_platform.IS_WINDOWS else 'Игра')
            file.write_bytes(b'test')
            library=launcher.Library(Path(directory)/'data')
            library.save_custom({'name':'Игра 日本語 🎮','path':str(file)})
            self.assertEqual(launcher.Library(Path(directory)/'data').state['custom'][0]['name'],'Игра 日本語 🎮')

    @unittest.skipUnless(orbit_platform.IS_WINDOWS, 'Requires the Windows command line parser')
    def test_windows_argument_parser_preserves_paths(self):
        args=orbit_platform.split_windows_arguments(r'--name "two words" --save "C:\My Games\saves"')
        self.assertEqual(args,['--name','two words','--save',r'C:\My Games\saves'])

    def test_null_arguments_rejected(self):
        with self.assertRaises(ValueError):
            launcher.parse_arguments('--test\0bad')


if __name__=='__main__':
    unittest.main()
