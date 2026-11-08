import json
from pathlib import Path
import sys,tempfile,unittest,os,subprocess
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import Library
from orbit_imports import detect_download

class ImportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.folder=self.root/'downloads';self.folder.mkdir()
  self.library=Library(self.root/'state')
 def download(self,names):
  for name in names:
   file=self.folder/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'test')
  return {'id':'torrent-1','name':'My game','path':str(self.folder),'files':names}
 def test_portable_game_added_once_and_survives_restart(self):
  item=self.download(['Game/Game.exe','Game/unins000.exe','Game/Redist/vcredist_x64.exe'])
  with patch('launcher.platform.IS_WINDOWS',True):game=self.library.import_download(item)
  self.assertEqual(game['path'],str(self.folder/'Game/Game.exe'));self.assertFalse(game['needsSetup'])
  self.assertIsNone(self.library.import_download(item))
  self.assertIsNone(Library(self.root/'state').import_download(item))
  self.assertEqual(len(self.library.state['custom']),1)
 def test_installer_or_archive_creates_configuration_card(self):
  game=self.library.import_download(self.download(['Setup/setup.exe','Setup/game.bin']))
  self.assertTrue(game['needsSetup']);self.assertEqual(game['path'],'')
  with patch('launcher.scan_steam',return_value=[]):
   self.assertFalse(self.library.refresh()[0]['installed'])
  with self.assertRaises(ValueError):self.library.launch(game['id'])
 def test_multiple_candidates_are_not_guessed(self):
  result=detect_download(self.download(['first.exe','second.exe']),True)
  self.assertTrue(result['needsSetup']);self.assertEqual(len(result['candidates']),2)
 def test_existing_game_is_not_duplicated_and_removed_card_stays_removed(self):
  item=self.download(['Game.exe'])
  with patch('launcher.platform.IS_WINDOWS',True),patch('launcher.parse_arguments',return_value=[]):
   gid=self.library.save_custom({'path':str(self.folder/'Game.exe'),'name':'Already added'})
   self.assertIsNone(self.library.import_download(item))
  self.assertEqual(len(self.library.state['custom']),1)
  self.library.state['custom']=[];self.library.save()
  self.assertIsNone(self.library.import_download(item))
 def test_linux_exe_uses_detected_proton(self):
  with patch('launcher.platform.IS_WINDOWS',False),patch('launcher.steam_roots',return_value=[]),patch('launcher.services.proton_versions',return_value=[{'path':'/proton/proton','name':'Proton'}]):
   game=self.library.import_download(self.download(['Game.exe']))
  self.assertEqual(game['runner'],'proton');self.assertFalse(game['needsSetup'])
 def test_files_outside_torrent_and_path_escape_are_ignored(self):
  item=self.download(['Game/setup.exe']);(self.folder/'unrelated.exe').write_bytes(b'x')
  item['files'].append('../unrelated.exe')
  self.assertEqual(detect_download(item,True)['candidates'],[])

class UserInstallTests(unittest.TestCase):
 @unittest.skipIf(os.name=='nt','Linux user package layout')
 def test_versioned_install_and_atomic_current_switch(self):
  from orbit_services import install_user_bundle
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);payload=root/'payload/opt/orbit';payload.mkdir(parents=True)
   package=root/'app.pkg.tar.zst';install=root/'installed'
   for version in ('0.2.3','0.2.4'):
    binary=payload/'orbit';binary.write_text('#!/bin/sh\necho '+version+'\n');binary.chmod(0o755)
    subprocess.run(['tar','--zstd','-cf',str(package),'-C',str(root/'payload'),'opt/orbit'],check=True)
    installed=install_user_bundle(package,install,version)
    self.assertEqual(subprocess.check_output([str(installed),'--version'],text=True).strip(),version)
    self.assertEqual((install/'current').resolve(),install/version)
   self.assertTrue((install/'0.2.3/orbit').exists())
   self.assertTrue((install/'.orbit-user-install.json').exists())

if __name__=='__main__':unittest.main()
