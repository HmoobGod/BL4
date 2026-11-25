"""Synthetic gear category integration; no game/SDK execution."""
import types
import unittest
import test_r3_persistent
from test_batch import Attr

class FGbxDefPtr:
    def __init__(self, name='LuckCategory_Gear', category=0, modifier=0):
        self._name=name; self._type=types.SimpleNamespace(Name='LuckCategoryDef')
        self.CategoryType=category; self.ModifierType=modifier
    def _get_address(self): return id(self)

class Entry:
    def __init__(self, name='LuckCategory_Gear', value=2., category=0):
        self.Category=FGbxDefPtr(name, category); self.Value=Attr(value)
    def _get_address(self): return id(self)

class GearLuck(unittest.TestCase):
    def setUp(self):
        self.p=test_r3_persistent.Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.m,self.f=self.p.m,self.p.f
        self.f.pc._path_name=lambda: "Local.OakPlayerController"
        self.gear=Entry();self.formula=Entry('LuckCategory_Base', 4., 1)
        self.entries=[self.formula,self.gear]
        self.f.pc.LuckCategoryAttributesState=types.SimpleNamespace(LuckCategories=self.entries)
    def activate(self, value):
        self.p.configure(gear_luck=value);self.p.tick()
    def test_default_off(self):
        self.assertFalse(self.m.AUTO_OPTIONS['gear_luck'].value)
        self.m.apply({'gear_luck':3.,'persistent_master':True,'persistent_offline':True});self.p.tick()
        self.assertEqual(self.gear.Value.writes,[])
    def test_update_restore(self):
        self.activate(2.5);self.assertEqual((self.gear.Value.Value,self.gear.Value.BaseValue),(5.,5.))
        self.m.apply({'gear_luck':3.});self.p.tick();self.assertEqual(self.gear.Value.Value,6.)
        self.m.apply({'gear_luck':1.});self.p.tick();self.assertEqual((self.gear.Value.Value,self.gear.Value.BaseValue),(2.,2.))
        self.assertEqual(self.formula.Value.writes,[]);self.assertEqual(self.f.writes,[])
    def test_missing(self):
        self.entries.pop();self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_duplicate(self):
        self.entries.append(Entry());self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_formula(self):
        self.gear.Category.CategoryType=1;self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_wrong_modifier(self):
        self.gear.Category.ModifierType=3;self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_zero(self):
        self.gear.Value=Attr(0.);self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_multiplayer(self):
        self.f.players=2;self.activate(3.);self.assertEqual(self.gear.Value.writes,[])
    def test_relocation_no_stale_write(self):
        self.activate(3.);replacement=Entry(value=6.);self.entries[1]=replacement;self.p.tick()
        self.assertTrue(self.m._controller.fault);self.assertEqual(replacement.Value.writes,[])
    def test_drift(self):
        self.activate(3.);self.gear.Value.Value=7.;self.p.tick()
        self.assertTrue(self.m._controller.fault);self.assertEqual(self.gear.Value.Value,7.)
    def test_feature_off(self):
        self.activate(3.);self.m.set_auto_setting(self.m.AUTO_OPTIONS['gear_luck'],False);self.p.tick()
        self.assertEqual(self.gear.Value.Value,2.)
    def test_increment(self):
        from bl4_custom_foundation.gameplay_fields import target_values
        with self.assertRaises(ValueError):target_values('gear_luck',(2.,),((1,'Value','ZFloatProperty'),),1.15)
