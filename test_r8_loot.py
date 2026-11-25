"""R8 rarity adjustments, synthetic SDK only; no game or reward execution."""
import unittest
import test_r3_persistent
from struct import pack, unpack

class RarityControls(unittest.TestCase):
    def setUp(self):
        self.p = test_r3_persistent.Persistent(); self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.m, self.f, self.r = self.p.m, self.p.f, self.p.e.r
    def test_new_opt_ins_default_off(self):
        for k in ('common_weight','uncommon_weight'):
            self.assertFalse(self.m.AUTO_OPTIONS[k].value)
        self.m.apply({'common_weight':0.,'uncommon_weight':0.,'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.assertEqual(self.r.CommonModifier.writes,[]); self.assertEqual(self.r.UncommonModifier.writes,[])
    def test_zero_live_restore(self):
        self.p.configure(common_weight=0.); self.p.tick()
        self.assertEqual(self.r.CommonModifier.Value,0.)
        self.p.tick(); self.assertEqual(self.r.CommonModifier.Value,0.)
        self.m.apply({'common_weight':2.5}); self.p.tick(); self.assertEqual(self.r.CommonModifier.Value,2.5)
        self.m.apply({'common_weight':1.}); self.p.tick(); self.assertEqual(self.r.CommonModifier.Value,1.)
        self.assertFalse(self.m._controller.fault)
        self.assertEqual(self.r.CommonModifier.BaseValue,1.)
    def test_two_zero_join_restores(self):
        self.p.configure(common_weight=0.,uncommon_weight=0.); self.p.tick(); self.p.tick()
        self.assertEqual((self.r.CommonModifier.Value,self.r.UncommonModifier.Value),(0.,0.))
        self.f.players=2; self.p.tick()
        self.assertEqual((self.r.CommonModifier.Value,self.r.UncommonModifier.Value),(1.,1.))
        self.assertFalse(self.m._controller.fault)
    def test_positive_baseline_required(self):
        self.r.CommonModifier._values['Value']=0.; self.p.configure(common_weight=2.); self.p.tick()
        self.assertEqual(self.r.CommonModifier.writes,[])
    def test_no_consent(self):
        self.p.configure(common_weight=0.); self.m.apply({'persistent_offline':False}); self.p.tick()
        self.assertEqual(self.r.CommonModifier.writes,[])
    def test_master_off_restore_zero(self):
        self.p.configure(uncommon_weight=0.); self.p.tick(); self.m.set_auto_setting(self.m.auto_master,False); self.p.tick()
        self.assertEqual(self.r.UncommonModifier.Value,1.)
    def test_higher_rarity_zero_refused(self):
        from bl4_custom_foundation.gameplay_fields import target_values
        for k in ('rare_weight','epic_weight','legendary_weight'):
            with self.assertRaises(ValueError): target_values(k,(1.,),((1,'Value','ZFloatProperty'),),0.)
    def test_fractional_legendary(self):
        self.p.configure(legendary_weight=2.7); self.p.tick()
        self.assertEqual(self.f.weight,unpack('<f',pack('<f',2.7))[0])
        self.m.apply({'legendary_weight':1.}); self.p.tick(); self.assertEqual(self.f.weight,1.)
    def test_weight_bounds(self):
        from bl4_custom_foundation.gameplay_fields import FEATURES,target_values
        for k in self.m.RARITY_KEYS:
            self.assertEqual(FEATURES[k][2],10.)
            for bad in (-.1,10.1,2.55,float('nan')):
                with self.assertRaises(ValueError): target_values(k,(1.,),((1,'Value','ZFloatProperty'),),bad)
    def test_preview_controls_never_active(self):
        for k in ('progress_enemy_xp','progress_money','progress_eridium','overall_loot_luck'):
            self.assertNotIn(k,self.m.AUTO_OPTIONS)
        self.m.apply({'progress_enemy_xp':5.,'progress_money':5.,'progress_eridium':5.,'overall_loot_luck':5.,'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.assertIsNone(self.m._controller)
    def test_numeric_input_saved_then_reconciled(self):
        self.p.configure(common_weight=2.); self.p.tick()
        self.m.open_key.callback(); self.m._category=2
        ui=self.p.b.gui.imgui
        ui.input_float=lambda label,value,*args: (True,0.) if label=='Value##numeric_common_weight' else (False,value)
        self.m.draw(); self.assertEqual(self.r.CommonModifier.Value,2.)
        self.m.flush_auto_edits(force=True); self.p.tick(); self.assertEqual(self.r.CommonModifier.Value,0.)
    def test_foreign_value_not_overwritten(self):
        self.p.configure(common_weight=0.); self.p.tick(); self.r.CommonModifier._values['Value']=7.; self.p.tick()
        self.assertEqual(self.r.CommonModifier.Value,7.); self.assertTrue(self.m._controller.fault)
    def test_alias_collision(self):
        self.r.UncommonModifier=self.r.CommonModifier
        self.p.configure(common_weight=0.5,uncommon_weight=2.); self.p.tick(); self.p.tick()
        self.assertEqual(self.r.CommonModifier.Value,1.); self.assertFalse(self.m._controller.records)
