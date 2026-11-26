"""Synthetic R12 sprint-only F8 integration with the existing R10 fixture."""
import unittest
from test_ground_speed import Ground

class Sprint(unittest.TestCase):
    def setUp(self):
        self.g = Ground(); self.g.setUp(); self.addCleanup(self.g.doCleanups)
        self.m, self.c = self.g.m, self.g.c
    def activate(self, value=2.):
        self.g.b.activate('sprint', value); self.g.tick()
    def test_default_off_and_manual_only(self):
        self.assertNotIn('sprint', self.m.AUTO_OPTIONS)
        self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
        self.g.tick(); self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_walk_unchanged_and_sprint_raised(self):
        self.activate(); self.assertIn('sprint',self.m._controller.records)
        self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
        self.c.bIsSprinting=True; self.g.tick(); self.assertEqual(self.c.MinAnalogWalkSpeed,1656.)
        self.c.bIsSprinting=False; self.g.tick(); self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_positive_floor_and_restore(self):
        self.c.MinAnalogWalkSpeed=120.; self.c.bIsSprinting=True
        self.activate(); self.assertEqual(self.c.MinAnalogWalkSpeed,1656.)
        self.activate(1.); self.assertEqual(self.c.MinAnalogWalkSpeed,120.)
    def test_combined_mode_conflict_preserves_original(self):
        self.g.start(); self.activate(); self.assertIn('walk_speed',self.m._controller.records)
        self.assertNotIn('sprint',self.m._controller.records); self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_reverse_conflict(self):
        self.c.bIsSprinting=True; self.activate(); self.g.queue(); self.g.tick()
        self.assertIn('sprint',self.m._controller.records); self.assertEqual(self.c.MinAnalogWalkSpeed,1656.)
    def test_foreign_drift(self):
        self.activate(); self.c.MinAnalogWalkSpeed=777.; self.g.tick()
        self.assertTrue(self.m._controller.fault); self.assertEqual(self.c.MinAnalogWalkSpeed,777.)
    def test_stale_callback(self):
        self.c.bIsSprinting=True; self.activate(); self.m._ground_seen=0.; self.m.monitor_tick()
        self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_other_player(self):
        self.c.bIsSprinting=True; self.g.b.activate('sprint',2.); self.g.tick(self.g.enemy)
        self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_join_restores(self):
        self.c.bIsSprinting=True; self.activate(); self.g.b.f.players=2; self.m.monitor_tick()
        self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_invalid_range(self):
        self.c.bIsSprinting=True; self.activate(4.); self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
