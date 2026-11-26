"""Persistent ammo-mode exclusion and UI selection regressions; synthetic only."""
from test_combat_r32 import PersistentReload
from test_combat_r13 import attr, desc

class PersistentAmmo(PersistentReload):
    def setUp(self):
        super().setUp(); p=self.r.p; self.a=attr(2.); p.ammoregenrate=self.a; p._path_name=lambda:'LocalPawn'
        prior=list(getattr(p.Class,'_properties',lambda:[])()); p.Class._properties=lambda:prior+[desc('ammoregenrate',self.a._type)]
    def values(self): return self.a.Value,self.rate.Value,self.delay.Value
    def test_default_off(self):
        self.m.apply({'player_ammo_regen':2.}); self.arm(); self.assertFalse(self.a.writes)
    def test_live_master_restore(self):
        self.arm(player_ammo_regen=2.,jump=1.5); self.assertEqual(self.values(),(4.,2.,4.)); self.assertEqual(set(self.m._automation_leases),{'reload','vacuum'})
        self.m.apply({'player_ammo_regen':3.}); self.tick(); self.assertEqual(self.a.Value,6.)
        self.m.set_auto_setting(self.m.auto_master,False); self.tick(); self.assertEqual(self.values(),(2.,2.,4.))
    def test_conflict_startup(self):
        self.arm(player_ammo_regen=2.,ammo_regen_rate=2.,ammo_regen_delay=2.,jump=1.5); self.assertFalse(self.a.writes+self.rate.writes+self.delay.writes); self.assertIn('jump',self.m._controller.records); self.assertEqual(set(self.m._automation_leases),{'reload','vacuum'}); self.assertIn('choose',self.m.persistent_feature_status('player_ammo_regen'))
    def test_player_to_weapon(self):
        self.arm(player_ammo_regen=2.); self.m.apply({'persistent_ammo_regen_rate':True,'ammo_regen_rate':3.}); self.tick(); self.assertEqual(self.values(),(2.,2.,4.)); self.assertFalse(self.rate.writes)
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['player_ammo_regen'],False); self.tick(); self.assertEqual(self.values(),(2.,6.,4.)); self.assertNotIn('player_ammo_regen',self.m._controller.records)
    def test_weapon_to_player(self):
        self.arm(ammo_regen_rate=2.,ammo_regen_delay=2.); self.m.apply({'persistent_player_ammo_regen':True,'player_ammo_regen':3.}); self.tick(); self.assertEqual(self.values(),(2.,2.,4.)); self.assertFalse(self.a.writes)
        self.m.apply({'persistent_ammo_regen_rate':False,'persistent_ammo_regen_delay':False}); self.tick(); self.assertEqual(self.values(),(6.,2.,4.))
    def test_atomic_switch(self):
        self.arm(ammo_regen_rate=2.,ammo_regen_delay=2.); self.m.apply({'persistent_ammo_regen_rate':False,'persistent_ammo_regen_delay':False,'persistent_player_ammo_regen':True,'player_ammo_regen':2.}); self.tick(); self.assertEqual(self.values(),(4.,2.,4.)); self.assertEqual(set(self.m._controller.records),{'player_ammo_regen'})
    def test_restore_fault_never_applies_replacement(self):
        self.arm(ammo_regen_rate=2.); self.rate._values['Value']=7.; self.m.apply({'persistent_ammo_regen_rate':False,'persistent_player_ammo_regen':True,'player_ammo_regen':2.}); self.tick(); self.assertTrue(self.m._controller.fault); self.assertFalse(self.a.writes)
    def test_zero_or_unequal_wait(self):
        self.a._values.update(Value=0.,BaseValue=0.); self.arm(player_ammo_regen=2.,jump=1.5); self.assertFalse(self.a.writes); self.assertIn('jump',self.m._controller.records)
        self.a._values.update(Value=2.,BaseValue=3.); self.tick(); self.assertFalse(self.a.writes)
        self.a._values.update(Value=2.,BaseValue=2.); self.tick(); self.assertEqual(self.a.Value,4.)
    def test_join_restore(self):
        self.arm(player_ammo_regen=2.); self.r.b.f.players=2; self.tick(); self.assertEqual(self.a.Value,2.); self.assertFalse(self.m._automation_leases)
    def test_draft_no_early_switch(self):
        self.arm(player_ammo_regen=2.); self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY['player_ammo_regen'],1.); self.m.apply({'persistent_ammo_regen_rate':True,'ammo_regen_rate':2.}); self.tick(); self.assertEqual(self.values(),(2.,2.,4.)); self.assertFalse(self.rate.writes); self.tick(3); self.assertEqual(self.values(),(2.,2.,4.)); self.assertFalse(self.rate.writes)
        self.m.flush_auto_edits(force=True); self.tick(); self.assertEqual(self.values(),(2.,4.,4.))
    def test_inactive_weapon_one_x_no_conflict(self):
        self.arm(player_ammo_regen=2.); self.m.apply({'persistent_ammo_regen_rate':True,'ammo_regen_rate':1.}); self.tick(); self.assertEqual(self.a.Value,4.)
    def test_ui_draft_lazy_normalize(self):
        o=self.m._PREVIEW_BY_KEY['player_ammo_regen']; self.m._auto_edits[o.identifier]=2.; self.m._pending[o.identifier]=3.; old=self.m.normalize
        self.m.normalize=lambda *a: (_ for _ in ()).throw(AssertionError('eager normalization'))
        try:
            self.assertEqual(self.m.displayed_selection(o),2.); self.m._auto_edits.clear(); self.assertEqual(self.m.displayed_selection(o),3.)
        finally:self.m.normalize=old
        self.m._pending.clear(); self.assertEqual(self.m.displayed_selection(o),1.)
