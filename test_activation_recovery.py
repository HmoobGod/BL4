import unittest
from types import SimpleNamespace as N
from test_r3_persistent import Persistent

class ActivationRecovery(unittest.TestCase):
    def setUp(self):
        self.p=Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.m=self.p.m;self.now=100.;self.m.time=N(monotonic=lambda:self.now)
    def tick(self,dt=.3):
        self.now+=dt;self.p.tick()
    def arm(self):
        self.p.configure(walk_speed=2.,legendary_weight=3.)
        self.tick();self.tick();self.m.ground_tick(self.p.anim)
        self.assertIn('walk_speed',self.m._controller.records);self.assertEqual(self.p.f.weight,3.)
    def test_stale_restores_ground_only_then_rearms(self):
        self.arm();self.tick(2.1)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.);self.assertEqual(self.p.f.weight,3.)
        self.assertFalse(self.m._auto_blocked);self.assertIsNotNone(self.m._auto_ground)
        self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.);self.assertEqual(self.p.f.writes,[3.])
    def test_expired_queue_keeps_rarity(self):
        self.p.configure(walk_speed=2.,legendary_weight=3.);self.tick();self.tick();old=self.m._auto_ground
        self.tick(3.1);self.assertFalse(self.m._auto_blocked);self.assertEqual(self.p.f.weight,3.)
        self.assertGreater(self.m._auto_ground[1],old[1]);self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.)
    def test_join_during_stale_restores_all(self):
        self.arm();self.p.f.players=2;self.tick(2.1)
        self.assertEqual(self.p.f.weight,1.);self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.);self.assertIsNone(self.m._auto_ground)
    def test_foreign_ground_drift_still_faults_and_restores_peer(self):
        self.arm();self.p.b.jump.MinAnalogWalkSpeed=777.;self.tick(2.1)
        self.assertTrue(self.m._controller.fault);self.assertEqual(self.p.f.weight,1.);self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,777.)
    def test_missing_ground_hook_keeps_rarity(self):
        self.m.ensure_ground_hook=lambda:False
        self.p.configure(walk_speed=2.,legendary_weight=3.);self.tick()
        self.assertEqual(self.p.f.weight,3.);self.assertFalse(self.m._auto_blocked)
    def test_idle_admission_backoff_skips_preflight(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_automation_reload':True})
        self.m._automation_next=self.now+.25
        self.m.automation_permitted=lambda:self.fail('idle backoff should not inspect')
        self.m.automation_tick()
    def test_player_count_reason_without_relaxing_gate(self):
        self.p.f.players=2;self.p.configure(legendary_weight=3.);self.tick()
        self.assertIn('player count is 2',self.m._auto_status);self.assertEqual(self.p.f.writes,[])
