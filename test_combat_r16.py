"""Mock-only local weapon field regressions."""
import unittest
from test_combat_r13 import Combat, attr, desc

class WeaponTuning(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.b=self.c.w.behaviors[0]
        self.spread=attr(4.); self.recoil=attr(2.)
        self.b.spread=self.spread; self.b.RecoilScale=self.recoil
        old=self.b.Class._properties()
        self.b.Class._properties=lambda:old+[desc('spread', self.spread._type),desc('RecoilScale', self.recoil._type)]
    def test_independent_cycles(self):
        self.c.activate('weapon_spread',.5); self.c.activate('weapon_recoil',.5)
        self.assertEqual(self.c.vals(self.spread),(2.,2.)); self.assertEqual(self.c.vals(self.recoil),(1.,1.))
        self.c.activate('weapon_spread',1.); self.assertEqual(self.c.vals(self.spread),(4.,4.)); self.assertEqual(self.c.vals(self.recoil),(1.,1.))
        self.c.activate('weapon_recoil',1.); self.assertEqual(self.c.vals(self.recoil),(2.,2.))
    def test_manual_and_inactive(self):
        for k in ('weapon_spread','weapon_recoil'): self.assertFalse(self.c.m.AUTO_OPTIONS[k].value)
        self.assertEqual(self.spread.writes+self.recoil.writes,[])
    def test_mode_change(self):
        self.c.activate('weapon_spread',.5); self.c.activate('weapon_recoil',.5)
        self.c.w.CurrentUseModeIndex=1; self.c.m.monitor_tick()
        self.assertEqual(self.c.vals(self.spread),(4.,4.)); self.assertEqual(self.c.vals(self.recoil),(2.,2.))
    def test_ordinary_gun_only(self):
        self.c.w.Class.Name='HeavyWeaponGadget'; self.c.activate('weapon_spread',.5)
        self.assertEqual(self.spread.writes,[])
    def test_unknown_field_refused(self):
        self.b.Class._properties=lambda:[]; self.c.activate('weapon_recoil',.5)
        self.assertEqual(self.recoil.writes,[])
    def test_join_restore(self):
        self.c.activate('weapon_recoil',.5); self.c.b.f.players=2; self.c.m.monitor_tick()
        self.assertEqual(self.c.vals(self.recoil),(2.,2.))
    def test_foreign_drift(self):
        self.c.activate('weapon_spread',.5); self.spread._values['Value']=3.; self.c.m.monitor_tick()
        self.assertTrue(self.c.m._controller.fault); self.assertEqual(self.spread.Value,3.)
    def test_zero_baseline_refused(self):
        self.spread._values.update(Value=0.,BaseValue=0.); self.c.activate('weapon_spread',.5)
        self.assertEqual(self.spread.writes,[])
    def test_no_replacement(self):
        self.c.activate('weapon_recoil',.5); self.c.p.ActiveWeapons.Slots=[]; self.c.m.monitor_tick()
        self.assertTrue(self.c.m._controller.fault)
