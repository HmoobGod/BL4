import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import collect_native_ncs as c


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'game'
        self.paks = self.game / 'OakGame/Content/Paks'
        self.paks.mkdir(parents=True)
        self.index = {}
        self.data = b'\x01NCS' + b'x' * 28
        self.reads = []
        self.backend = SimpleNamespace(list_entries=lambda p: self.index[p], read_entry=self.read)
        self.output = self.root / 'evidence.zip'

    def pak(self, name, rows, parent=None):
        p = (parent or self.paks) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'p' * 512)
        self.index[p.resolve()] = rows
        return p.resolve()

    def entry(self):
        return (0, len(self.data), len(self.data), 0)

    def read(self, p, e):
        self.reads.append(p)
        return self.data

    def collect(self, patch_root=None, output=None):
        return c.collect(self.game, patch_root, output or self.output, self.backend)

    def test_select_only_target_rows_and_hash(self):
        p = self.pak('pakchunk0-Windows.pak', {'a/Nexus-Data-inv0.ncs': self.entry(),
            'a/Nexus-Data-attribute1.ncs': self.entry(), 'a/Nexus-Data-mission0.ncs': self.entry(),
            'a/Nexus-Data-inventory_container0.ncs': self.entry()})
        m = self.collect()
        self.assertEqual(m['coverage'], {'attribute': 1, 'inv': 1})
        self.assertEqual(self.reads, [p, p])
        self.assertEqual(m['files'][0]['sha256'], hashlib.sha256(self.data).hexdigest())
        with zipfile.ZipFile(self.output) as z:
            self.assertEqual(set(z.namelist()), {'ncs/Nexus-Data-inv0.ncs', 'ncs/Nexus-Data-attribute1.ncs', 'manifest.json'})
            self.assertEqual(json.loads(z.read('manifest.json')), m)

    def test_newest_patch_wins(self):
        name = 'Nexus-Data-inv0.ncs'
        self.pak('pakchunk0-Windows.pak', {name: self.entry()})
        self.pak('pakchunk0-Windows_1_P.pak', {name: self.entry()})
        newest = self.pak('pakchunk0-Windows_2_P.pak', {name: self.entry()})
        m = self.collect()
        self.assertEqual(self.reads, [newest])
        self.assertEqual(m['files'][0]['pak'], newest.name)

    def test_deletion_shadows_older(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry(), 'Nexus-Data-attribute0.ncs': self.entry()})
        self.pak('pakchunk0-Windows_1_P.pak', {'Nexus-Data-inv0.ncs': None})
        m = self.collect()
        self.assertEqual(len(m['deleted']), 1)
        self.assertEqual(m['coverage'], {'attribute': 1})

    def test_ambiguous_same_priority(self):
        self.pak('pakchunk0-Windows.pak', {'x/Nexus-Data-inv0.ncs': self.entry(), 'y/Nexus-Data-INV0.ncs': self.entry()})
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.collect()
        self.assertFalse(self.output.exists())

    def test_mod_pak_excluded(self):
        p = self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        self.pak('SomeMod_99_P.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        self.collect()
        self.assertEqual(self.reads, [p])

    def test_official_downloaded_patch(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        patch_root = self.root / 'patch'
        p = self.pak('pakchunk0-Windows_5_P.pak', {'Nexus-Data-inv0.ncs': self.entry()}, patch_root / 'v5')
        self.collect(patch_root)
        self.assertEqual(self.reads, [p])

    def test_bad_index_never_falls_back(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        bad = self.pak('pakchunk0-Windows_1_P.pak', {})
        original = self.backend.list_entries
        def index(p):
            if p == bad: raise OSError('index failure')
            return original(p)
        self.backend.list_entries = index
        with self.assertRaisesRegex(ValueError, 'cannot read index'):
            self.collect()
        self.assertEqual(self.reads, [])

    def test_bad_payload_removes_partial_archive(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        self.backend.read_entry = lambda *_: b'broken'
        with self.assertRaisesRegex(ValueError, 'invalid NCS payload'):
            self.collect()
        self.assertFalse(self.output.exists())

    def test_reject_output_in_game(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.collect(output=self.game / 'evidence.zip')

    def test_no_overwrite(self):
        self.output.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new .zip'):
            self.collect()
        self.assertEqual(self.output.read_bytes(), b'keep')

    def test_size_limit(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': (0, c.MAX_FILE+1, 32, 0)})
        with self.assertRaisesRegex(ValueError, 'oversized'):
            self.collect()
        self.assertEqual(self.reads, [])

    def test_mutating_source_fails(self):
        self.pak('pakchunk0-Windows.pak', {'Nexus-Data-inv0.ncs': self.entry()})
        def read(p, _):
            p.write_bytes(b'changed')
            return self.data
        self.backend.read_entry = read
        with self.assertRaisesRegex(ValueError, 'changed during read'):
            self.collect()
        self.assertFalse(self.output.exists())

    def test_pinned_backend_rejects_changed_source(self):
        p = self.root / 'pakncs.py'
        p.write_text('raise RuntimeError("must not run")')
        with self.assertRaisesRegex(ValueError, 'reviewed Git blob'):
            c.load_backend(p)

    def test_pinned_backend_does_not_run_main(self):
        p = self.root / 'pakncs.py'
        p.write_text('def list_entries(p): return {}\ndef read_entry(p,e): return b""\nif __name__ == "__main__": raise RuntimeError("must not run")\n')
        with patch.object(c, 'BACKEND_SHA', c.git_blob_sha(p.read_bytes())):
            self.assertEqual(c.load_backend(p).list_entries(p), {})

    def test_no_implicit_oodle_library_load(self):
        c.configure_oodle(self.backend, None)
        with self.assertRaisesRegex(ValueError, 'requires --oodle'):
            self.backend.oodle(b'a', 1)

    def test_oodle_path_explicit(self):
        p = self.root / 'oo2core_9_win64.dll'
        p.write_bytes(b'fixture, not executed')
        c.configure_oodle(self.backend, p)
        self.assertEqual(self.backend.OODLE_DLL, str(p.resolve()))
        with self.assertRaisesRegex(ValueError, 'must identify'):
            other = self.root / 'other.dll'
            other.write_bytes(b'fixture')
            c.configure_oodle(self.backend, other)

    def test_exact_target_names(self):
        for s in ('Nexus-Data-inv4.ncs', 'Nexus-Data-attribute0.ncs', 'Nexus-Data-loot_config12.ncs', 'Nexus-Data-inv_stat_2.ncs'):
            self.assertIsNotNone(c._target(s))
        for s in ('Nexus-Data-inv_name_part1.ncs', 'Nexus-Data-inv4.ncs.bak', 'Nexus-Data-inv4.exe'):
            self.assertIsNone(c._target(s))


    def test_reward_consumer_tables_collected_without_unrelated_data(self):
        names=('Nexus-Data-itempool0.ncs','Nexus-Data-itempoollist1.ncs','Nexus-Data-gbx_ue_data_table0.ncs')
        self.pak('pakchunk0-Windows.pak',{n:self.entry() for n in (*names,'Nexus-Data-mission0.ncs','Nexus-Data-itempool_preview0.ncs')})
        newest=self.pak('pakchunk0-Windows_2_P.pak',{names[0]:self.entry()})
        result=self.collect()
        self.assertEqual(result['coverage'],{'itempool':1,'itempoollist':1,'gbx_ue_data_table':1})
        self.assertEqual({r['name'] for r in result['files']},set(names))
        self.assertEqual(next(r['pak'] for r in result['files'] if r['name']==names[0]),newest.name)


if __name__ == '__main__':
    unittest.main()
