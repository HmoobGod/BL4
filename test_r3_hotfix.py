import unittest
from test_r3_persistent import Persistent

class LiveGroundUpdate(unittest.TestCase):
    def setUp(self):
        self.p=Persistent(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.p.configure(walk_speed=2); self.p.tick(); self.p.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.)
    def change(self):
        m=self.p.m
        m.queue_auto_edit(m._ground_selection,1.5); m.flush_auto_edits(force=True); self.p.tick()
        self.assertIsNotNone(m._auto_ground)
    def test_baseline_reset_during_live_update(self):
        self.change(); self.p.b.jump.MinAnalogWalkSpeed=0.; self.p.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,810.)
        self.assertEqual(self.p.m._controller.records['walk_speed']['selection'],1.5)
        self.p.m.set_auto_setting(self.p.m.auto_master,False); self.p.tick()
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_foreign_value_during_live_update(self):
        self.change(); self.p.b.jump.MinAnalogWalkSpeed=777.; self.p.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,777.)
        self.assertTrue(self.p.m._controller.fault)

class PersistentDiagnostics(unittest.TestCase):
    def setUp(self):
        self.p=Persistent(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
    def test_blocking_status_only_reported_once(self):
        self.p.f.solo=False; self.p.f.players=2; self.p.configure(walk_speed=2); self.p.tick()
        m=self.p.m
        lines=[x for x in m._live_lines if x.startswith('Persistent status:')]
        self.assertEqual(len(lines),1); self.assertIn('eligible local solo session',lines[0])
        self.p.tick(); self.assertEqual([x for x in m._live_lines if x.startswith('Persistent status:')],lines)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
