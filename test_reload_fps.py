"""Owner FPS-directed persistent reload observer; synthetic, not native timing."""
import unittest
from unittest.mock import patch
from test_combat_r13 import Combat, attr, Node

class ReloadFPS(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.c.activate('reload',2.)
        self.ctrl=self.c.m._controller
        self.g=self.ctrl.tick.__globals__
        self.w=self.g['weapon_rates']
        self.now=100.
        p=patch.dict(self.g,{'monotonic':lambda:self.now});p.start();self.addCleanup(p.stop)
        self.tick()
        self.assertIn('reload_watch',self.ctrl.records['reload'])
    def tick(self, dt=.01):
        self.now+=dt
        return self.ctrl.tick(True,follow_weapon=True)
    def test_steady_no_descriptor_scan_and_bounded_full_audit(self):
        with patch.object(self.w,'prop',wraps=self.w.prop) as prop:
            for _ in range(5):self.tick()
            self.assertEqual(prop.call_count,0)
            self.tick(.11)
            self.assertGreater(prop.call_count,0)
        self.assertEqual(self.c.reload.Value,1.5)
    def test_live_floor_checked_before_next_full_audit(self):
        self.c.minimum._values.update(Value=2.,BaseValue=2.)
        self.tick();self.assertEqual(self.c.reload.Value,3.)
        self.assertFalse(self.ctrl.records)
    def test_pending_swap_restores_only_reload(self):
        self.c.activate('repair_health',2.)
        self.c.p.ActiveWeapons.Slots[0].PendingWeapon=self.c.w
        self.assertEqual(self.tick(),{'reload'})
        self.assertEqual(self.c.reload.Value,3.)
        self.assertEqual(self.c.health.Value,40.)
    def test_replaced_weapon_never_written(self):
        other=self.c.weapon(attr(4.),attr(4.),attr(.5))
        self.c.p.ActiveWeapons.Slots=[self.c.slot(other)]
        self.tick();self.assertTrue(self.ctrl.fault)
        self.assertFalse(other.behaviors[1].ReloadTime.writes)
    def test_foreign_value_not_overwritten(self):
        self.c.reload._values['Value']=1.75
        self.tick();self.assertTrue(self.ctrl.fault)
        self.assertEqual(self.c.reload.Value,1.75)
    def test_join_restores_immediately(self):
        self.c.b.f.players=2
        self.tick();self.assertFalse(self.ctrl.records)
        self.assertEqual(self.c.reload.Value,3.)
    def test_metadata_change_same_type_detected_at_full_audit(self):
        b=self.c.w.behaviors[1];old=b.Class._properties
        b.Class._properties=lambda:[p for p in old() if p.Name!='MinReloadTime']
        self.tick(.11);self.assertEqual(self.c.reload.Value,3.)
        self.assertFalse(self.ctrl.records)
    def test_write_has_fresh_floor_guard(self):
        r=self.ctrl.records['reload'];self.c.minimum._values.update(Value=2.,BaseValue=2.)
        before=list(self.c.reload.writes)
        with self.assertRaisesRegex(ValueError,'native minimum'):
            self.ctrl.write_one(r,0,1.5,applying=True)
        self.assertEqual(self.c.reload.writes,before)
    def test_mode_transition_before_audit(self):
        self.c.w.CurrentUseModeIndex=1
        self.assertEqual(self.tick(),{'reload'})
        self.assertEqual(self.c.reload.Value,3.)
    def test_duplicate_behavior_detected_before_audit(self):
        self.c.w.behaviors.append(self.c.w.behaviors[1])
        self.tick();self.assertTrue(self.ctrl.fault)
        self.assertEqual(self.c.reload.Value,1.5)
