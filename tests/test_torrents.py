"""Transfer a generated torrent over loopback; no external trackers or content."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import libtorrent as lt
from orbit_services import Torrents


class TorrentTests(unittest.TestCase):
    def test_local_transfer_pause_restart_and_keep_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); seed=root/'seed'; seed.mkdir(); dest=root/'dest'; dest.mkdir()
            payload=os.urandom(256*1024); (seed/'sample.bin').write_bytes(payload)
            storage=lt.file_storage(); lt.add_files(storage,str(seed/'sample.bin'))
            creator=lt.create_torrent(storage); lt.set_piece_hashes(creator,str(seed))
            torrent=root/'sample.torrent'; torrent.write_bytes(lt.bencode(creator.generate()))
            settings={'listen_interfaces':'127.0.0.1:0','enable_dht':False,'enable_lsd':False,'enable_upnp':False,'enable_natpmp':False}
            seeder=lt.session(settings)
            params=lt.add_torrent_params(); params.ti=lt.torrent_info(str(torrent)); params.save_path=str(seed)
            seed_handle=seeder.add_torrent(params)
            client=Torrents(root/'state'); client.data.mkdir(parents=True); client.lt=lt; client.session=lt.session(settings)
            client.add(str(torrent),str(dest)); tid=next(iter(client.handles))
            handle=client.handles[tid]
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if seed_handle.status().is_seeding: break
                time.sleep(.05)
            handle.connect_peer(('127.0.0.1',seeder.listen_port()))
            while time.monotonic()<deadline:
                if handle.status().is_seeding: break
                time.sleep(.1)
            self.assertTrue(handle.status().is_seeding,'Loopback torrent did not finish')
            self.assertEqual((dest/'sample.bin').read_bytes(),payload)
            completed=client.completed()
            self.assertEqual(completed[0]['files'],['sample.bin'])
            client.entries[tid]['autoAdd']=False
            self.assertEqual(client.completed(),[])
            client.entries[tid]['autoAdd']=True
            client.action(tid,'pause'); self.assertTrue(client.status()['items'][0]['paused'])
            client.session.remove_torrent(handle)
            restored=Torrents(root/'state'); restored.data.mkdir(exist_ok=True); restored.lt=lt; restored.session=lt.session(settings)
            import json
            for entry in json.loads((client.data/'queue.json').read_text()): restored._add(entry)
            self.assertTrue(restored.status()['items'][0]['paused'])
            restored.action(tid,'resume'); self.assertFalse(restored.status()['items'][0]['paused'])
            restored.action(tid,'remove'); self.assertEqual(restored.status()['items'],[])
            self.assertEqual((dest/'sample.bin').read_bytes(),payload)
            seeder.pause(); client.session.pause(); restored.session.pause()
            client.handles.clear(); restored.handles.clear()
            client.session=None; restored.session=None
            del seeder


if __name__=='__main__': unittest.main()
