import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from test_combat_r13 import Combat, attr, Node
from test_r3_persistent import Persistent

class HandoffRecovery(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.m=self.c.m; self.f=self.c.b.f; self.f.solo=True
        self.m.close_menu(); self.c.b.gui.finish_close()
        self.now=100.; self.m.time=N(monotonic=lambda:self.now)
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_reload':True,'reload':2.})
        self.tick(); self.assertEqual(self.c.reload.Value,1.5)
        self.newrate=attr(4.); self.new=self.c.weapon(attr(8.),self.newrate,attr(.5));self.new.CurrentState='Inactive'
        self.c.p.ActiveWeapons.Slots.append(self.c.slot(self.new))
    def tick(self,dt=.01):
        self.now+=dt; self.m.monitor_tick()
    def equip(self):
        self.c.w.CurrentState='Inactive';self.new.CurrentState='Active';self.c.p.ActiveWeapons.Slots[0].PendingWeapon=None
    def pending(self):
        self.c.p.ActiveWeapons.Slots[0].PendingWeapon=self.new; self.tick()
        self.assertEqual(self.c.reload.Value,3.);self.assertFalse(self.newrate.writes)
    def test_ready_swap_same_callback(self):
        self.equip();self.tick();self.assertEqual(self.c.reload.Value,3.);self.assertEqual(self.newrate.Value,2.)
    def test_pending_then_ready_before_normal_reconcile(self):
        self.pending();self.equip();self.tick(.06);self.assertEqual(self.newrate.Value,2.);self.assertIsNone(self.m._reload_handoff)
    def test_retry_bounded(self):
        self.pending();ctrl=self.m._controller
        with patch.object(ctrl,'capture',wraps=ctrl.capture) as capture:
            for _ in range(4):self.tick(.01)
            self.assertEqual(capture.call_count,0)
            self.tick(.02);self.assertEqual(capture.call_count,1)
    def test_join_while_pending_never_writes(self):
        self.pending();self.equip();self.f.players=2;self.tick(.06);self.assertFalse(self.newrate.writes);self.assertIsNone(self.m._reload_handoff)
    def test_disable_while_pending_never_writes(self):
        self.pending();self.equip();self.m.set_auto_setting(self.m.AUTO_OPTIONS['reload'],False);self.tick(.06);self.assertFalse(self.newrate.writes)
    def test_native_floor_still_blocks(self):
        self.new.behaviors[1].MinReloadTime._values.update(Value=3.,BaseValue=3.)
        self.equip();self.tick();self.assertEqual(self.c.reload.Value,3.);self.assertFalse(self.newrate.writes)
    def test_no_pending_work_in_steady_state(self):
        with patch.object(self.m,'fast_reload_handoff',wraps=self.m.fast_reload_handoff) as fast:
            for _ in range(5):self.tick()
            self.assertEqual(fast.call_count,0)

class GroundRearm(unittest.TestCase):
    def setUp(self):
        self.p=Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups);self.m=self.p.m
        self.now=100.;self.m.time=N(monotonic=lambda:self.now)
        self.p.configure(walk_speed=2.,legendary_weight=3.)
        self.tick();self.tick(.3);self.m.ground_tick(self.p.anim)
        self.assertIn('walk_speed',self.m._controller.records)
    def tick(self,dt=.01):
        self.now+=dt;self.m.monitor_tick()
    def test_replacement_animation_before_stale(self):
        new=Node();self.p.f.pawn.Mesh.GetAnimInstance=lambda:new
        self.tick(.3);self.p.b.jump.bIsSprinting=True;self.m.ground_tick(new)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1656.);self.assertEqual(self.p.f.weight,3.)
        self.assertEqual(self.m._ground_seen,self.now)
    def test_stale_requeues_even_before_reconciliation(self):
        self.now+=2.1;self.m._auto_next=self.now+.2;self.m.monitor_tick()
        self.assertIsNotNone(self.m._auto_ground);self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.);self.assertEqual(self.p.f.weight,3.)
    def test_no_heartbeat_fabrication(self):
        old=self.m._ground_seen;self.p.f.pawn.Mesh.GetAnimInstance=lambda:Node();self.tick(.3)
        self.assertEqual(self.m._ground_seen,old)
    def test_steady_camera_does_not_query_mesh(self):
        with patch.object(self.p.f.pawn.Mesh,'GetAnimInstance',wraps=self.p.f.pawn.Mesh.GetAnimInstance) as mesh:
            self.tick(.1);self.assertEqual(mesh.call_count,0)
