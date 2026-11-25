"""R6 fire-only experiment. Mock SDK; does not measure damage in the game."""
import unittest
import test_r3_persistent

class FireExperiment(unittest.TestCase):
    def setUp(self):
        self.p = test_r3_persistent.Persistent(); self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.m, self.b, self.f = self.p.m, self.p.b, self.p.f
        self.a = self.b.fire
    def values(self): return self.a.Value, self.a.BaseValue
    def test_default_disabled(self):
        self.assertFalse(self.m.AUTO_OPTIONS['fire_damage'].value)
        self.m.apply({'fire_damage':2.,'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.assertEqual(self.a.writes,[])
    def test_opt_in_update_restore(self):
        self.p.configure(fire_damage=2.); self.p.tick(); self.assertEqual(self.values(),(2.,2.))
        self.m.apply({'fire_damage':3.}); self.p.tick(); self.assertEqual(self.values(),(3.,3.))
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['fire_damage'],False); self.p.tick(); self.assertEqual(self.values(),(1.,1.))
    def test_join_restore(self):
        self.p.configure(fire_damage=2.); self.p.tick(); self.f.players=2; self.p.tick()
        self.assertEqual(self.values(),(1.,1.)); self.assertFalse(self.m._controller.records)
    def test_master_off_restore(self):
        self.p.configure(fire_damage=2.); self.p.tick(); self.m.set_auto_setting(self.m.auto_master,False); self.p.tick(); self.assertEqual(self.values(),(1.,1.))
    def test_no_consent(self):
        self.p.configure(fire_damage=2.); self.m.apply({'persistent_offline':False}); self.p.tick(); self.assertEqual(self.a.writes,[])
    def test_baseline_mismatch(self):
        self.a._values['Value']=1.5; self.p.configure(fire_damage=2.); self.p.tick(); self.assertEqual(self.a.writes,[]); self.assertIn('Activation failed',self.m._auto_blocked)
    def test_partial_write_rollback(self):
        self.a.reject='BaseValue'; self.p.configure(fire_damage=2.); self.p.tick(); self.assertEqual(self.values(),(1.,1.)); self.assertFalse(self.m._controller.fault)
    def test_only_fire_changed(self):
        self.p.configure(fire_damage=2.); self.p.tick(); self.assertEqual(self.values(),(2.,2.))
        pawn=self.f.pawn
        for name in ('ShockModifier','CorrosiveModifier','CryoModifier','RadiationModifier'):
            self.assertEqual(getattr(pawn.ElementalDamageModifiers,name).writes,[])
        self.assertEqual(pawn.DamageCauserData.DamageDealtMultiplier.writes,[])
    def test_combined_with_movement_restore(self):
        self.p.configure(fire_damage=2.,walk_speed=2.); self.p.tick(); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.assertEqual(self.values(),(2.,2.)); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1080.)
        self.m.set_auto_setting(self.m.auto_master,False); self.p.tick(); self.assertEqual(self.values(),(1.,1.)); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
