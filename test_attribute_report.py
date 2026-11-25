import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from test_foundation import Test

class AttributeTests(unittest.TestCase):
    def setUp(self):
        self.base = Test(); self.base.setUp(); self.m = self.base.m
        self.old_sdk = sys.modules.get('unrealsdk')
    def tearDown(self):
        self.base.tearDown()
        if self.old_sdk is None: sys.modules.pop('unrealsdk', None)
        else: sys.modules['unrealsdk'] = self.old_sdk
    def sdk(self, names):
        def find_all(cls, exact):
            if cls == 'ScriptStruct': return []
            return [types.SimpleNamespace(Name=n, NumParams=1, _path_name=lambda n=n: '/Script/GbxGame.GbxAttributeBlueprintLibrary:'+n,
                _properties=lambda: [types.SimpleNamespace(Name='ContextSource')]) for n in names]
        return types.SimpleNamespace(find_all=find_all)
    def test_exact_api_names(self):
        report,count=self.m.attribute_report(self.sdk(self.m.ATTRIBUTE_API+('Other',)))
        self.assertEqual(count,3); self.assertNotIn(':Other',report); self.assertIn('ContextSource',report)
    def test_missing(self):
        report,count=self.m.attribute_report(self.sdk(())); self.assertEqual(count,0); self.assertIn('0 candidate(s)',report)
    def test_duplicate(self):
        report,count=self.m.attribute_report(self.sdk((self.m.ATTRIBUTE_API[0],)*5)); self.assertEqual(count,1); self.assertIn('truncated',report)
    def test_disabled_no_scan(self):
        self.m.mod.is_enabled=False; self.m.attribute_report=lambda sdk: self.fail('unexpected scan'); self.m.inspect_attribute_compatibility()
    def test_file_and_explicit_f8_check(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'report.txt'; self.m.report_path=lambda:f
            sys.modules['unrealsdk']=self.sdk(self.m.ATTRIBUTE_API)
            self.base.open(); self.assertFalse(f.exists()); self.m._category=1
            self.base.gui.imgui.clicks={'Run read-only reward compatibility check'}; self.m.draw()
            self.assertTrue(f.is_file()); self.assertIn('3/3',self.m._reward_summary); self.assertEqual(self.m.mod.save_count,0)
            self.assertIn('No native reward or modifier function invoked',f.read_text())
    def test_report_failure_console(self):
        self.m.report_path=lambda:None; sys.modules['unrealsdk']=self.sdk(())
        with contextlib.redirect_stdout(io.StringIO()) as output: self.m.inspect_attribute_compatibility()
        self.assertIn('Report file unavailable',self.m._reward_summary); self.assertIn('0 candidate(s)',output.getvalue())
    def test_scan_failure(self):
        self.m.report_path=lambda:None; sys.modules['unrealsdk']=types.SimpleNamespace(find_all=lambda *a,**k: (_ for _ in ()).throw(RuntimeError()))
        with contextlib.redirect_stdout(io.StringIO()) as output: self.m.inspect_attribute_compatibility()
        self.assertIn('scan failed (RuntimeError)',output.getvalue()); self.assertIn('HOLD',self.m._reward_summary)
    def test_archive_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'sdk_mods'; (root/'settings').mkdir(parents=True)
            self.m.__file__=str(root/'bl4_custom_foundation.sdkmod'/'bl4_custom_foundation'/'__init__.py')
            self.assertEqual(self.m.report_path(),root/'settings'/'bl4_custom_reward_report.txt')
    def test_unexpected_path(self):
        self.m.__file__='/not-a-game/mod.py'; self.assertIsNone(self.m.report_path())
    def test_no_game_calls(self):
        import ast,inspect
        tree=ast.parse(inspect.getsource(self.m.attribute_report))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in self.m.ATTRIBUTE_API for n in ast.walk(tree)))
        self.assertEqual(self.m.mod.hooks,[])

if __name__=='__main__': unittest.main(defaultTest='AttributeTests',verbosity=2)
