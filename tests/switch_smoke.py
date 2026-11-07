"""Qt account-switch lifecycle checks, without starting or stopping real Steam."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow
from launcher import Library, create_bridge

app = QApplication([])


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = QMainWindow()
        self.window.resize(1000, 700)
        self.window.show()
        self.library = Library(Path(self.temp.name))
        self.library.games = [{'id':'steam-42','appid':'42','source':'steam','accountId':'second'}]
        self.account = {'id':'second','name':'Second','login':'second-login','root':'/test/Steam'}
        self.bridge = create_bridge(self.window, self.library)
        self.messages = []
        self.bridge.launchFinished.connect(lambda raw: self.messages.append(json.loads(raw)))
        self.accounts = patch('launcher.steam_accounts',return_value=[self.account]).start()
        self.processes = patch('launcher.steam_processes',return_value=[]).start()
        self.active = patch('launcher.active_steam_account',return_value='main').start()
        self.running = patch('launcher.running_steam_games',return_value=False).start()
        self.spawn = patch('launcher.subprocess.Popen').start()
        self.which = patch('launcher.shutil.which',return_value='/usr/bin/steam').start()
        self.command = patch('launcher.steam_command',return_value=['steam']).start()
        self.minimize = patch('launcher.minimize_steam_library',return_value=1).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.bridge.timer.stop)
        self.addCleanup(self.window.close)

    def request(self, action):
        return json.loads(self.bridge.request(action, json.dumps({'id':'steam-42'})))

    def topmost(self):
        return bool(self.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_switch_covers_steam_and_cancel_restores_window(self):
        self.assertTrue(self.request('switchAndLaunch')['switching'])
        self.assertTrue(self.topmost())
        self.assertTrue(self.window.isFullScreen())
        self.request('cancelSwitch')
        self.assertFalse(self.topmost())
        self.assertFalse(self.window.isFullScreen())
        self.assertIsNone(self.bridge.pending)

    def test_start_waits_for_selected_login_without_launching_game(self):
        self.request('switchAndLaunch')
        self.bridge.pending['quietSince'] = time.monotonic()-2
        self.bridge.poll_switch()
        self.assertEqual(self.spawn.call_args.args[0],['steam','-silent','-login','second-login'])
        self.assertEqual(self.bridge.pending['phase'],'login')
        self.bridge.poll_switch()
        self.assertEqual(self.spawn.call_count,1)
        self.minimize.assert_not_called()
        self.assertTrue(self.topmost())

    def test_matching_account_minimizes_library_and_releases_before_game(self):
        self.request('switchAndLaunch')
        self.bridge.pending.update(phase='login',readySince=time.monotonic()-2)
        self.active.return_value='second'
        def launch(game_id):
            self.assertFalse(self.topmost(), 'Orbit must not cover the game')
            return {'ok':True}
        with patch.object(self.library,'launch',side_effect=launch) as launch_mock:
            self.bridge.poll_switch()
            launch_mock.assert_called_once_with('steam-42')
        self.minimize.assert_called_once()
        self.assertIsNone(self.bridge.pending)
        self.assertEqual(self.messages[-1],{'ok':True})

    def test_show_steam_explicitly_releases_cover(self):
        self.request('switchAndLaunch')
        self.request('showSteam')
        self.assertFalse(self.topmost())
        self.assertIsNotNone(self.bridge.pending)
        self.assertEqual(self.spawn.call_args.args[0],['steam','steam://open/main'])

    def test_login_timeout_releases_cover_without_launching(self):
        self.request('switchAndLaunch')
        self.bridge.pending.update(phase='login',deadline=time.monotonic()-1)
        self.bridge.poll_switch()
        self.assertFalse(self.topmost())
        self.assertIsNone(self.bridge.pending)
        self.assertIn('error',self.messages[-1])
        self.spawn.assert_not_called()

    def test_running_game_refuses_switch_and_does_not_cover(self):
        self.running.return_value=True
        self.assertIn('error',self.request('switchAndLaunch'))
        self.assertFalse(self.topmost())
        self.spawn.assert_not_called()


    def test_shader_setting_restart_does_not_launch_any_game(self):
        self.bridge.request('setShaderSkip',json.dumps({'enabled':True}))
        self.assertTrue(Library(Path(self.temp.name)).state['skipShaderPrecache'])
        with patch('launcher.steam_roots',return_value=[Path('/test/Steam')]):
            self.assertTrue(self.request('restartSteam')['switching'])
        self.bridge.pending['quietSince']=time.monotonic()-2
        self.bridge.poll_switch()
        self.assertEqual(self.spawn.call_args.args[0],['steam','-silent'])
        self.assertEqual(self.spawn.call_args.kwargs['env']['STEAM_ENABLE_SHADER_CACHE_MANAGEMENT'],'0')
        self.bridge.pending['readySince']=time.monotonic()-2
        with patch.object(self.library,'launch') as launch:
            self.bridge.poll_switch()
            launch.assert_not_called()
        self.assertEqual(self.messages[-1],{'ok':True,'settingsApplied':True})
        self.assertFalse(self.topmost())
        self.assertEqual(self.library.state['recent'],{})

    def test_shader_restart_does_not_stop_a_running_game(self):
        self.running.return_value=True
        self.assertIn('error',self.request('restartSteam'))
        self.spawn.assert_not_called()
        self.assertIsNone(self.bridge.pending)


if __name__=='__main__':
    unittest.main()
