import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_services import Saves, SaveConflict, Updater, digest, game_command, proton_versions


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b, self.cloud = [self.root / n for n in ('a', 'b', 'cloud')]
        for path in (self.a, self.b, self.cloud): path.mkdir()
        self.sa, self.sb = Saves(self.root/'state-a'), Saves(self.root/'state-b')
        self.pa = {'local': str(self.a), 'cloud': str(self.cloud), 'key': 'same-game'}
        self.pb = {**self.pa, 'local': str(self.b)}

    def test_two_computers_conflict_restore_and_history(self):
        (self.a/'save.dat').write_text('one')
        first = self.sa.sync('a',self.pa)['history'][0]['id']
        self.sb.sync('b', self.pb)
        self.assertEqual((self.b/'save.dat').read_text(), 'one')
        (self.a/'save.dat').write_text('from-a')
        (self.b/'save.dat').write_text('from-b')
        self.sa.sync('a',self.pa)
        with self.assertRaises(SaveConflict): self.sb.sync('b',self.pb)
        self.assertEqual((self.b/'save.dat').read_text(), 'from-b')
        self.sb.sync('b', self.pb, 'cloud')
        self.assertEqual((self.b/'save.dat').read_text(), 'from-a')
        backups=list((self.sb.data/'save-backups').glob('*/save.dat'))
        self.assertEqual(backups[0].read_text(), 'from-b')
        self.sb.sync('b', self.pb, snapshot_id=first)
        self.assertEqual((self.b/'save.dat').read_text(), 'one')
        self.assertEqual(len(self.sa.history(self.pa)), 2)

    def test_first_sync_never_overwrites_nonempty_other_computer(self):
        (self.a/'save').write_text('a'); (self.b/'save').write_text('b')
        self.sa.sync('a',self.pa)
        with self.assertRaises(SaveConflict): self.sb.sync('b',self.pb)
        self.sb.sync('b',self.pb,'local')
        self.assertEqual(len(self.sb.history(self.pb)), 2)

    def test_corrupt_remote_leaves_local_untouched(self):
        (self.a/'save').write_text('a'); self.sa.sync('a',self.pa)
        archive=next(self.cloud.rglob('*.zip')); archive.write_bytes(b'broken')
        with self.assertRaises(ValueError): self.sb.sync('b',self.pb)
        self.assertEqual(list(self.b.iterdir()), [])

    def test_nested_folders_and_symlinks_rejected(self):
        with self.assertRaises(ValueError): self.sa.locations({**self.pa,'cloud':str(self.a)})
        if os.name!='nt':
            (self.a/'escape').symlink_to(self.cloud, target_is_directory=True)
            with self.assertRaises(ValueError): self.sa.sync('a',self.pa)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.updater=Updater(self.temp.name,'0.1.0')
        self.release={'tag_name':'v0.2.0','body':'Changes','assets':[
            {'name':'orbit_0.2.0_amd64.deb','browser_download_url':'https://github.com/Sttanors/orbit-launcher/releases/download/v0.2.0/orbit_0.2.0_amd64.deb'},
            {'name':'SHA256SUMS-linux.txt','browser_download_url':'https://github.com/Sttanors/orbit-launcher/releases/download/v0.2.0/SHA256SUMS-linux.txt'}]}

    def test_verified_download_and_corruption(self):
        import hashlib
        package=b'valid installer'; checksum=hashlib.sha256(package).hexdigest()
        def response(url, **kwargs): return io.BytesIO((checksum+'  orbit_0.2.0_amd64.deb\n').encode() if str(url).endswith('.txt') else package)
        with patch.object(self.updater,'fetch_json',return_value=self.release), patch.object(self.updater,'package',return_value=('_amd64.deb','SHA256SUMS-linux.txt')), patch('urllib.request.urlopen',side_effect=response):
            self.assertTrue(self.updater.download()['ready'])
            self.assertEqual(self.updater.ready.read_bytes(), package)
        self.updater.ready=None
        def bad(url, **kwargs): return io.BytesIO((checksum+'  orbit_0.2.0_amd64.deb\n').encode() if str(url).endswith('.txt') else b'corrupt')
        with patch.object(self.updater,'fetch_json',return_value=self.release), patch.object(self.updater,'package',return_value=('_amd64.deb','SHA256SUMS-linux.txt')), patch('urllib.request.urlopen',side_effect=bad):
            with self.assertRaises(ValueError): self.updater.download()
        self.assertIsNone(self.updater.ready)
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_check_compares_numeric_versions(self):
        self.updater.version='0.9.0'
        with patch.object(self.updater,'fetch_json',return_value={'tag_name':'v0.10.0'}):
            self.assertTrue(self.updater.check()['available'])


class ProtonTests(unittest.TestCase):
    def test_isolated_prefix_and_literal_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); script=root/'steamapps/common/Proton Test/proton'; script.parent.mkdir(parents=True); script.write_text('')
            game={'id':'local-123','path':str(root/'game with spaces.exe'),'runner':'proton','proton':str(script)}
            self.assertIn(str(script), [p['path'] for p in proton_versions([root])])
            command,env=game_command(game,root/'data',[root])
            self.assertEqual(command,[str(script),'waitforexitandrun',game['path']])
            self.assertEqual(env['STEAM_COMPAT_DATA_PATH'],str(root/'data/prefixes/local-123'))


if __name__=='__main__': unittest.main()
