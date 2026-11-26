"""Synthetic event and polling coexistence, not proof BL4 dispatches OnJumped."""
import unittest,sys,types
from unittest.mock import patch
from test_double_jump_r52 import JumpVelocity
from test_combat_r13 import Node
from test_foundation import Test

class JumpEvent(JumpVelocity):
    def fast_first(self):
        self.ground=False;self.fall=True;self.pawn.JumpCurrentCount=self.comp.JumpedCount=1;self.goal._name='JumpGoal_Default';self.vel.Z=800.
        self.now+=.01;self.lane.tick(True,event_pawn=self.pawn)
    def fast_second(self,actor=None):
        self.pawn.JumpCurrentCount=self.comp.JumpedCount=2;self.goal._name='JumpGoal_DoubleJump';self.vel.Z=800.
        self.now+=.01;self.lane.tick(True,event_pawn=actor or self.pawn)
    def test_fast_second_before_poll_due(self):
        self.start();self.fast_first();self.fast_second();self.assertEqual(self.vel.Z,1200.);self.assertEqual(self.lane.applied,1)
        self.lane.tick(True,event_pawn=self.pawn);self.tick();self.assertEqual(self.lane.applied,1)
    def test_foreign_event_no_mutation(self):
        self.start();self.fast_first();self.fast_second(Node());self.assertEqual(self.lane.phase,'first');self.assertEqual(self.vel.Z,800.)
        self.tick();self.assertEqual(self.vel.Z,1200.)
    def test_early_event_falls_back(self):
        self.start();self.fast_first();self.goal._name='JumpGoal_DoubleJump';self.pawn.JumpCurrentCount=2;self.vel.Z=800.
        self.lane.tick(True,event_pawn=self.pawn);self.assertEqual(self.lane.phase,'first');self.assertEqual(self.vel.Z,800.)
        self.comp.JumpedCount=2;self.tick();self.assertEqual(self.vel.Z,1200.)
    def test_event_never_skips_first(self):
        self.start();self.ground=False;self.fall=True;self.fast_second();self.assertEqual(self.vel.Z,800.)
    def test_event_does_not_shift_poll_due(self):
        self.start();due=self.lane.next_due;self.fast_first();self.fast_second();self.assertEqual(self.lane.next_due,due)
    def test_event_scope_loss(self):
        self.start();self.fast_first();self.ok=False;self.fast_second();self.assertEqual(self.vel.Z,800.);self.assertIsNone(self.lane.record)
    def test_early_second_wrong_velocity_then_poll(self):
        self.start();self.fast_first();self.pawn.JumpCurrentCount=self.comp.JumpedCount=2;self.goal._name='JumpGoal_DoubleJump';self.vel.Z=100.
        self.lane.tick(True,event_pawn=self.pawn);self.assertEqual(self.lane.phase,'first');self.vel.Z=800.;self.tick();self.assertEqual(self.vel.Z,1200.)
    def test_event_while_busy(self):
        self.start();self.fast_first();self.lane.busy=True;self.fast_second();self.assertEqual(self.vel.Z,800.);self.lane.busy=False

class Registration(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown);self.m=self.base.m
        self.hooks=types.SimpleNamespace(Type=types.SimpleNamespace(POST='post'))
        self.members={};self.calls=[]
        self.hooks.has_hook=lambda p,k,i:(p,k,i) in self.members
        def add(p,k,i,fn):self.calls.append(i);self.members[p,k,i]=fn;return True
        self.hooks.add_hook=add
        self.fn=Node(Name='OnJumped',NumParams=0,_properties=lambda:[],Outer=Node(_path_name=lambda:'/Script/Engine.Character'),_path_name=lambda:self.m._JUMP_EVENT_PATH)
        self.sdk=types.SimpleNamespace(hooks=self.hooks,find_all=lambda *a,**k:[self.fn]);self.mock=patch.dict(sys.modules,{'unrealsdk':self.sdk});self.mock.start();self.addCleanup(self.mock.stop)
    def test_exact_registration(self):self.assertTrue(self.m.ensure_jump_event());self.assertTrue(self.m.ensure_jump_event());self.assertEqual(len(self.calls),1)
    def test_no_foreign_adoption(self):
        self.members[self.m._JUMP_EVENT_PATH,'post',self.m._JUMP_EVENT_ID]=lambda *a:None;self.assertFalse(self.m.ensure_jump_event());self.assertEqual(self.calls,[])
    def test_missing_event(self):self.sdk.find_all=lambda *a,**k:[];self.assertFalse(self.m.ensure_jump_event());self.assertFalse(self.m._jump_event_owned)
    def test_wrong_signature(self):self.fn.NumParams=1;self.assertFalse(self.m.ensure_jump_event());self.assertEqual(self.calls,[])
    def test_false_add_but_inserted(self):
        add=self.hooks.add_hook
        def added(*a):add(*a);return False
        self.hooks.add_hook=added;self.assertTrue(self.m.ensure_jump_event())
    def test_dormant_callback(self):self.m.ensure_jump_event();self.m.jump_event_tick(None);self.assertFalse(self.m._automation_busy)
    def test_dispatch_gate(self):
        from bl4_custom_foundation.gameplay_fields import identity
        self.m.ensure_jump_event();pawn=Node();calls=[]
        lease=types.SimpleNamespace(record=(None,(None,identity(pawn)),1),fault=False,busy=False,tick=lambda *a,**kw:calls.append(kw))
        self.m._automation_leases['double_jump']=lease;self.m._monitor_thread=self.m.threading.get_ident();self.m.auto_master.value=True;self.m.auto_consent.value=True;self.m.AUTOMATION_OPTIONS['double_jump'].value=True
        self.m.automation_permitted=lambda:True
        self.m.jump_event_tick(Node());self.assertEqual(calls,[])
        self.m.jump_event_tick(pawn);self.assertEqual(calls,[{'event_pawn':pawn}]);self.assertFalse(self.m._automation_busy)
        self.m._monitor_thread=-1;self.m.jump_event_tick(pawn);self.assertEqual(len(calls),1)
    def test_fault_retained(self):
        from bl4_custom_foundation.gameplay_fields import identity
        self.m.ensure_jump_event();pawn=Node();stops=[]
        lease=types.SimpleNamespace(record=(None,(None,identity(pawn)),1),fault=False,busy=False)
        def tick(*a,**kw):lease.fault=True;lease.record=None;self.m._automation_leases.clear()
        lease.tick=tick;self.m._automation_leases['double_jump']=lease;self.m._monitor_thread=self.m.threading.get_ident();self.m.auto_master.value=True;self.m.auto_consent.value=True;self.m.AUTOMATION_OPTIONS['double_jump'].value=True;self.m.automation_permitted=lambda:True
        self.m.request_stop=lambda *a,**k:stops.append(a[0]);self.m.jump_event_tick(pawn);self.assertIs(self.m._automation_leases['double_jump'],lease);self.assertEqual(len(stops),1)
