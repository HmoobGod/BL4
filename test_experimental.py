"""Mock-only v0.7.0.dev1 admission, restoration and range tests."""
import unittest
import test_expansion

class Experimental(unittest.TestCase):
    def setUp(self):
        self.e = test_expansion.Expansion(); self.e.setUp(); self.addCleanup(self.e.doCleanups)
        self.b, self.m = self.e.b, self.e.m
        self.a = self.e.p.DamageState.DamageTakenMultiplier
    def test_no_startup_or_saved_selection_writes(self):
        self.m.apply({'damage_taken': .1, 'repair_cooldown': .1})
        self.m.draw(); self.m.monitor_tick()
        self.assertEqual(self.a.writes, []); self.assertEqual(self.b.cool.writes, [])
    def test_lower_damage_and_restore(self):
        self.b.activate('damage_taken', .1)
        self.assertAlmostEqual(self.a.Value, .1); self.assertEqual(self.a.Value, self.a.BaseValue)
        self.b.activate('damage_taken', 1.)
        self.assertEqual((self.a.Value, self.a.BaseValue), (1.,1.))
    def test_cooldown_two_seconds_then_restore(self):
        self.b.activate('repair_cooldown', .1)
        self.assertEqual((self.b.cool.Value,self.b.cool.BaseValue),(2.,2.))
        self.b.activate('repair_cooldown',1.)
        self.assertEqual((self.b.cool.Value,self.b.cool.BaseValue),(20.,20.))
    def test_below_range_fails_closed(self):
        self.b.activate('damage_taken', 0.)
        self.assertEqual(self.a.writes,[])
        self.b.activate('repair_cooldown', .01)
        self.assertEqual(self.b.cool.writes,[])
    def test_coop_rejected(self):
        self.b.f.players=2; self.b.activate('damage_taken',.5)
        self.assertEqual(self.a.writes,[])
    def test_join_restores_incoming(self):
        self.b.activate('damage_taken',.5); self.b.f.players=2; self.m.monitor_tick()
        self.assertEqual((self.a.Value,self.a.BaseValue),(1.,1.))
    def test_partial_pair_write_restores(self):
        self.a.reject='BaseValue'; self.b.activate('damage_taken',.5)
        self.assertEqual((self.a.Value,self.a.BaseValue),(1.,1.))
        self.assertFalse(self.m._controller.fault)
    def test_outgoing_still_blocked(self):
        self.b.activate('damage',2.)
        self.assertEqual(self.e.p.DamageCauserData.DamageDealtMultiplier.writes,[])
    def test_explicit_f8_activation(self):
        self.m._category=0; self.m.auto_consent.value=True
        self.b.gui.imgui.edits={'Damage taken multiplier##damage_taken':.5,'Enable Damage taken multiplier##persistent_damage_taken':True}
        self.m.draw(); self.assertEqual(self.a.writes,[]); self.m.monitor_tick()
        self.assertEqual(self.a.Value,.5)
