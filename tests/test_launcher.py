import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher import Library, read_vdf, app_names, scan_steam, account_from_connection_log, minimize_steam_library, start_steam


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_steam_text_paths_and_nesting(self):
        file = self.root / 'libraryfolders.vdf'
        file.write_text('"libraryfolders" { "1" { "path" "/games/My Library" "apps" { "42" "123" } } }')
        self.assertEqual(read_vdf(file)['libraryfolders']['1']['path'], '/games/My Library')

    def test_appinfo_v29(self):
        strings = [b'appid', b'common', b'name', b'type']
        payload = b'\0' * 60 + b'\x01' + struct.pack('<I', 2) + b'Example Game\0' + b'\x01' + struct.pack('<I', 3) + b'Game\0\x08'
        entry = struct.pack('<II', 42, len(payload)) + payload
        offset = 16 + len(entry) + 4
        file = self.root / 'appinfo.vdf'
        file.write_bytes(struct.pack('<IIQ', 0x07564429, 1, offset) + entry + b'\0'*4 + struct.pack('<I', len(strings)) + b'\0'.join(strings) + b'\0')
        self.assertEqual(app_names(file)['42'], {'name': 'Example Game', 'type': 'Game'})

    def test_scan_multiple_libraries_and_missing_disk(self):
        steam = self.root / 'Steam'
        (steam / 'steamapps/common/Example').mkdir(parents=True)
        (steam / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "/missing-disk" "apps" { "99" "100" } } }')
        (steam / 'steamapps/appmanifest_42.acf').write_text('"AppState" { "appid" "42" "name" "Example" "StateFlags" "4" "installdir" "Example" }')
        with patch('launcher.steam_roots', return_value=[steam]):
            result = {g['appid']:g for g in scan_steam()}
        self.assertTrue(result['42']['installed'])
        self.assertFalse(result['99']['installed'])

    def test_native_launch_keeps_arguments_literal_and_cwd(self):
        file = self.root / 'Game with spaces'
        file.write_text('#!/bin/sh\nexit 0\n')
        file.chmod(0o755)
        library = Library(self.root / 'data')
        library.games = [{'id':'local-1','source':'local','path':str(file),'arguments':'--name "two words" "$(touch unsafe)"'}]
        with patch('launcher.subprocess.Popen') as spawn:
            library.launch('local-1')
        self.assertEqual(spawn.call_args.args[0], [str(file), '--name', 'two words', '$(touch unsafe)'])
        self.assertEqual(spawn.call_args.kwargs['cwd'], str(self.root))
        self.assertIn('local-1', json.loads(library.path.read_text())['recent'])

    def test_steam_launch_uses_silent_applaunch(self):
        library = Library(self.root / 'data')
        library.games = [{'id':'steam-42','appid':'42','source':'steam'}]
        with patch('launcher.shutil.which', return_value='/usr/bin/steam'), patch('launcher.subprocess.Popen') as spawn:
            library.launch('steam-42')
        self.assertEqual(spawn.call_args.args[0], ['steam','-silent','-applaunch','42'])

    def test_missing_executable_does_not_record_launch(self):
        library = Library(self.root / 'data')
        library.games = [{'id':'local-1','source':'local','path':str(self.root/'missing')}]
        with self.assertRaisesRegex(ValueError, 'не найден'):
            library.launch('local-1')
        self.assertEqual(library.state['recent'], {})

    def test_saved_favorites_and_custom_game_survive_restart(self):
        library = Library(self.root / 'data')
        library.state['custom'] = [{'id':'local-1','source':'local','path':str(self.root/'missing'),'name':'Game'}]
        library.state['favorites'] = ['local-1']
        library.save()
        with patch('launcher.scan_steam', return_value=[]):
            result = Library(self.root / 'data').refresh()
        self.assertTrue(result[0]['favorite'])
        self.assertFalse(result[0]['installed'])


    def test_edit_preserves_id_favorites_recent_and_cover(self):
        file = self.root / 'my game'
        file.write_text('test')
        library = Library(self.root / 'data')
        gid = library.save_custom({'name':'Before','path':str(file)})
        library.state['favorites'] = [gid]
        library.state['recent'][gid] = 123
        library.state['custom'][0]['cover'] = 'file:///existing-cover.png'
        library.save_custom({'name':'After','path':str(file),'arguments':'--test "two words"','cwd':str(self.root)}, gid)
        saved = Library(self.root / 'data')
        self.assertEqual(len(saved.state['custom']),1)
        self.assertEqual(saved.state['custom'][0]['name'],'After')
        self.assertEqual(saved.state['custom'][0]['cover'],'file:///existing-cover.png')
        self.assertEqual(saved.state['favorites'],[gid])
        self.assertEqual(saved.state['recent'][gid],123)

    def test_invalid_edit_does_not_mutate_saved_game(self):
        file = self.root / 'game'
        file.write_text('test')
        library = Library(self.root / 'data')
        gid = library.save_custom({'name':'Original','path':str(file)})
        before = library.path.read_bytes()
        with self.assertRaises(ValueError):
            library.save_custom({'name':'Bad','path':str(file),'arguments':'"unterminated'},gid)
        self.assertEqual(library.path.read_bytes(), before)

    def test_account_mismatch_requests_switch_without_launch(self):
        library = Library(self.root / 'data')
        library.games = [{'id':'steam-42','appid':'42','source':'steam','accountId':'2'}]
        account = {'id':'2','login':'second','name':'Second'}
        with patch('launcher.steam_accounts',return_value=[account]), patch('launcher.active_steam_account',return_value='1'), patch('launcher.subprocess.Popen') as spawn:
            result = library.launch('steam-42')
        self.assertTrue(result['needsAccountSwitch'])
        spawn.assert_not_called()
        self.assertEqual(library.state['recent'],{})

    def test_confirmed_account_launches_only_via_silent_applaunch(self):
        library = Library(self.root / 'data')
        library.games = [{'id':'steam-42','appid':'42','source':'steam','accountId':'2'}]
        with patch('launcher.steam_accounts',return_value=[{'id':'2','login':'second','name':'Second'}]), patch('launcher.active_steam_account',return_value='2'), patch('launcher.shutil.which',return_value='/usr/bin/steam'), patch('launcher.subprocess.Popen') as spawn:
            library.launch('steam-42')
        self.assertEqual(spawn.call_args.args[0],['steam','-silent','-applaunch','42'])

    def test_account_binding_and_current_account_override(self):
        library = Library(self.root / 'data')
        library.games = [{'id':'steam-42','appid':'42','source':'steam','accountId':'2'}]
        with patch('launcher.steam_accounts',return_value=[{'id':'1','login':'main'}]):
            with self.assertRaises(ValueError):
                library.set_account('steam-42','unknown')
            library.set_account('steam-42','1')
            self.assertEqual(library.steam_target(library.games[0])['login'],'main')
            library.set_account('steam-42','')
            self.assertIsNone(library.steam_target(library.games[0]))

    def test_edit_can_remove_cover(self):
        file = self.root / 'game'
        file.write_text('test')
        library = Library(self.root / 'data')
        gid = library.save_custom({'name':'Game','path':str(file)})
        library.state['custom'][0]['cover'] = 'file:///existing.png'
        library.save_custom({'name':'Game','path':str(file),'clearCover':True},gid)
        self.assertEqual(library.state['custom'][0]['cover'],'')


    def test_current_account_uses_only_this_sessions_logon(self):
        from datetime import datetime
        stamp = datetime(2026, 11, 6, 21, 0).timestamp()
        line = '[2026-11-06 21:01:00] [Logged On, 3, 0] [U:1:123] RecvMsgClientLogOnResponse() : processing complete'
        self.assertEqual(account_from_connection_log(line,stamp),str(76561197960265728+123))
        self.assertEqual(account_from_connection_log(line,stamp+1000),'')
        self.assertEqual(account_from_connection_log(line+'\n[2026-11-06 21:02:00] [Logging Off, 3, 0] LogOff',stamp),'')


    def test_minimize_only_main_window_owned_by_steam(self):
        from types import SimpleNamespace
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            action, args = command[1],command[2:]
            values = {
                ('search',): '1 2 3 4',
                ('getwindowpid','1'): '123', ('getwindowname','1'): 'Steam',
                ('getwindowpid','2'): '999', ('getwindowname','2'): 'Steam',
                ('getwindowpid','3'): '123', ('getwindowname','3'): 'Sign in to Steam',
                ('getwindowpid','4'): '123', ('getwindowname','4'): 'Steam Guard',
            }
            key = (action,) if action=='search' else (action,*args)
            return SimpleNamespace(stdout=values.get(key,''),returncode=0)
        with patch.dict(os.environ,{'DISPLAY':':test'}), patch('launcher.shutil.which',return_value='/usr/bin/xdotool'), patch('launcher.steam_processes',return_value=[(123,['steam'])]), patch('launcher.subprocess.run',side_effect=run):
            self.assertEqual(minimize_steam_library(),1)
        self.assertEqual([c for c in commands if c[1]=='windowminimize'],[['xdotool','windowminimize','1']])

    def test_minimize_without_xdotool_is_optional(self):
        with patch('launcher.shutil.which',return_value=None), patch('launcher.subprocess.run') as run:
            self.assertEqual(minimize_steam_library(),0)
        run.assert_not_called()


    def test_shader_skip_is_scoped_to_spawned_steam_environment(self):
        with patch.dict(os.environ, {'ORBIT_TEST_ENV':'preserved'}), patch('launcher.steam_command',return_value=['steam']), patch('launcher.subprocess.Popen') as spawn:
            start_steam(None,['-silent'],True)
            self.assertEqual(spawn.call_args.kwargs['env']['STEAM_ENABLE_SHADER_CACHE_MANAGEMENT'],'0')
            self.assertEqual(spawn.call_args.kwargs['env']['ORBIT_TEST_ENV'],'preserved')
            self.assertEqual(spawn.call_args.args[0],['steam','-silent'])

    def test_flatpak_receives_shader_setting_explicitly(self):
        with patch('launcher.steam_command',return_value=['flatpak','run','com.valvesoftware.Steam']), patch('launcher.subprocess.Popen') as spawn:
            start_steam(None,['-silent'],True)
        self.assertEqual(spawn.call_args.args[0],['flatpak','run','--env=STEAM_ENABLE_SHADER_CACHE_MANAGEMENT=0','com.valvesoftware.Steam','-silent'])

    def test_shader_setting_survives_restart_and_game_launch_uses_it(self):
        library=Library(self.root/'data')
        library.state['skipShaderPrecache']=True
        library.save()
        library=Library(self.root/'data')
        library.games=[{'id':'steam-42','appid':'42','source':'steam'}]
        with patch('launcher.start_steam') as start:
            library.launch('steam-42')
        self.assertTrue(start.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
