"""Pearlescent rarity experiment: synthetic game objects only."""
import unittest
import test_r3_persistent
import test_batch
from struct import pack, unpack

class PearlControls(unittest.TestCase):
    def setUp(self):
        self.p = test_r3_persistent.Persistent(); self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.m, self.f, self.r = self.p.m, self.p.f, self.p.e.r
        self.a = test_batch.Attr(1.)
        self.r.PearlescentModifier = self.a

    def test_default_off(self):
        self.assertFalse(self.m.AUTO_OPTIONS['pearlescent_weight'].value)
        self.m.apply({'pearlescent_weight':2.1,'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.assertEqual(self.a.writes,[])

    def test_live_restore(self):
        self.p.configure(pearlescent_weight=2.1); self.p.tick()
        self.assertEqual(self.a.Value,unpack('<f',pack('<f',2.1))[0])
        self.m.apply({'pearlescent_weight':.1}); self.p.tick()
        self.assertEqual(self.a.Value,unpack('<f',pack('<f',.1))[0])
        self.m.apply({'pearlescent_weight':1.}); self.p.tick()
        self.assertEqual(self.a.Value,1.); self.assertEqual(self.a.BaseValue,1.)

    def test_secondary_alias(self):
        del self.r.PearlescentModifier; self.r.PearlModifier=self.a
        self.p.configure(pearlescent_weight=2.); self.p.tick(); self.assertEqual(self.a.Value,2.)

    def test_same_identity_alias(self):
        self.r.PearlModifier=self.a
        self.p.configure(pearlescent_weight=2.); self.p.tick(); self.assertEqual(self.a.Value,2.)

    def test_ambiguous_alias(self):
        self.r.PearlModifier=test_batch.Attr(1.)
        self.p.configure(pearlescent_weight=2.); self.p.tick()
        self.assertEqual(self.a.writes,[]); self.assertEqual(self.r.PearlModifier.writes,[])

    def test_missing_alias(self):
        del self.r.PearlescentModifier
        self.p.configure(pearlescent_weight=2.); self.p.tick()
        self.assertEqual(self.a.writes,[]); self.assertIn('Activation failed',self.m._auto_blocked)

    def test_join_restores(self):
        self.p.configure(pearlescent_weight=2.); self.p.tick(); self.f.players=2; self.p.tick()
        self.assertEqual(self.a.Value,1.); self.assertFalse(self.m._controller.records)

    def test_no_consent(self):
        self.p.configure(pearlescent_weight=2.); self.m.apply({'persistent_offline':False}); self.p.tick()
        self.assertEqual(self.a.writes,[])

    def test_master_off_restores(self):
        self.p.configure(pearlescent_weight=3.); self.p.tick(); self.m.set_auto_setting(self.m.auto_master,False); self.p.tick()
        self.assertEqual(self.a.Value,1.); self.assertFalse(self.m._controller.records)

    def test_no_other_rarity_write(self):
        self.p.configure(pearlescent_weight=2.); self.p.tick()
        for a in ('CommonModifier','UncommonModifier','RareModifier','VeryRareModifier'):
            self.assertEqual(getattr(self.r,a).writes,[])
        self.assertEqual(self.f.writes,[])

    def test_bounds_and_zero_hold(self):
        from bl4_custom_foundation.gameplay_fields import target_values
        for v in (0.,10.1,2.15,float('nan')):
            with self.assertRaises(ValueError): target_values('pearlescent_weight',(1.,),((1,'Value','ZFloatProperty'),),v)

    def test_foreign_drift_refuses_overwrite(self):
        self.p.configure(pearlescent_weight=2.); self.p.tick(); self.a._values['Value']=7.; self.p.tick()
        self.assertEqual(self.a.Value,7.); self.assertTrue(self.m._controller.fault)

    def test_alias_collision_with_existing_rarity(self):
        self.r.PearlescentModifier=self.r.RareModifier
        self.p.configure(rare_weight=2.,pearlescent_weight=3.); self.p.tick(); self.p.tick()
        self.assertEqual(self.r.RareModifier.Value,1.); self.assertFalse(self.m._controller.records)
