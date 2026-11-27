"""Persistent reload exact-reset recovery; mock observations, not native gameplay."""
import unittest
from test_handoff_recovery import HandoffRecovery

class ReloadPersistence(HandoffRecovery):
    def reset_pair(self):
        self.c.reload._values.update(Value=3., BaseValue=3.)
    def peer(self):
        self.m.apply({'persistent_repair_health':True,'repair_health':2.})
        self.tick(.3)
        self.assertIn('repair_health',self.m._controller.records)
    def test_exact_reset_preserves_peer_and_reapplies(self):
        self.peer();self.reset_pair();self.tick()
        self.assertEqual(self.c.health.Value,40.)
        self.assertFalse(self.m._auto_blocked)
        self.assertNotIn('reload',self.m._controller.records)
        self.tick(.26);self.assertEqual(self.c.reload.Value,1.5)
        self.assertEqual(self.c.health.Value,40.)
    def test_reset_while_reloading_waits_for_idle(self):
        self.reset_pair();self.c.w.CurrentState='Reloading';self.tick()
        self.tick(.26);self.assertEqual(self.c.reload.Value,3.)
        self.assertIn('idle',self.m._controller.reload_wait_reason)
        self.c.w.CurrentState='Active';self.tick(.06)
        self.assertEqual(self.c.reload.Value,1.5)
        self.assertEqual(self.m._controller.reload_wait_reason,'')
    def test_repeated_reset_rearm_is_bounded(self):
        self.reset_pair();self.tick();n=len(self.c.reload.writes)
        for _ in range(10):self.tick(.01)
        self.assertEqual(len(self.c.reload.writes),n)
        self.tick(.16);self.assertEqual(self.c.reload.Value,1.5)
    def test_foreign_pair_still_faults(self):
        self.peer();self.c.reload._values.update(Value=1.7,BaseValue=1.7);self.tick()
        self.assertTrue(self.m._controller.fault)
        self.assertEqual(self.c.reload.Value,1.7)
        self.assertEqual(self.c.health.Value,20.)
    def test_disable_after_reset_never_rearms(self):
        self.reset_pair();self.tick()
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['reload'],False);self.tick(.3)
        self.assertEqual(self.c.reload.Value,3.)
    def test_join_after_reset_never_rearms(self):
        self.reset_pair();self.tick();self.f.players=2;self.tick(.3)
        self.assertEqual(self.c.reload.Value,3.)
    def test_wait_reason_not_repeated_each_callback(self):
        self.pending();self.tick(.06)
        self.assertIn('transition pending',self.m._controller.reload_wait_reason)
        for _ in range(10):self.tick(.06)
        self.assertEqual(sum(x.startswith('WAIT reload:') for x in self.m._live_lines),1)
        self.equip();self.tick(.06)
        self.assertEqual(self.m._controller.reload_wait_reason,'')
    def test_native_floor_after_reset_still_blocks(self):
        self.reset_pair();self.tick()
        self.c.minimum._values.update(Value=2.,BaseValue=2.)
        self.tick(.26)
        self.assertEqual(self.c.reload.Value,3.)
        self.assertIn('native minimum',self.m._controller.reload_wait_reason)
