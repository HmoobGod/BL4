"""Cross-Fire event scope; simulated events only, not native gameplay."""
import unittest
from test_native_skill_r58 import NativeSkill
from test_combat_r13 import Node

class Crossfire(unittest.TestCase):
    def setUp(self):
        self.n=NativeSkill();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.s=self.n.s;self.m=self.n.m
        from bl4_custom_foundation.skill_pulse import CROSSFIRE_CLASS,CROSSFIRE_EVENTS
        self.cls=CROSSFIRE_CLASS;self.s.cls.Name=self.cls
        self.events=[];self.hooks=self.s.b.f.sdk.hooks
        self.hooks.Type.POST='eventpost';self.hooks.Type.PRE='eventpre'
        for name in CROSSFIRE_EVENTS:
            f=Node(Name=name,Outer=self.s.cls,NumParams=0,_path_name=lambda name=name:self.cls+':'+name,_properties=lambda:[])
            self.events.append(f);self.s.funcs.append(f)
    def arm(self,**kw):
        self.n.arm('duration',**{'crossfire_duration_events':True,**kw})
    def event(self,start,obj=None):
        p,k,t=self.m._crossfire_hooks[1][0 if start else 1]
        self.s.b.hooks[p,k,t](self.s.script if obj is None else obj)
    def trend(self):
        for x in (.75,.70,.65):self.s.advance(d=x)
    def test_default_off(self):self.assertFalse(self.m.CROSSFIRE_GATE.value)
    def test_waits_for_local_event(self):
        self.arm();self.trend();self.assertEqual(self.n.calls,[]);self.assertFalse(self.m._automation_leases['skill_duration'].event_active)
    def test_start_uses_fresh_samples(self):
        self.arm();self.s.advance(d=.7);self.event(True);self.s.advance(d=.69);self.s.advance(d=.68);self.assertEqual(self.n.calls,[]);self.s.advance(d=.67);self.assertEqual(len(self.n.calls),1)
    def test_end_stops_and_next_start_rearms(self):
        self.arm();self.event(True);self.trend();self.assertEqual(len(self.n.calls),1);self.event(False);self.s.advance(d=.6);self.s.advance(d=.55);self.assertEqual(len(self.n.calls),1);self.event(True);self.trend();self.assertEqual(len(self.n.calls),2)
    def test_foreign_script_no_start(self):
        self.arm();self.event(True,Node(Class=self.s.cls));self.trend();self.assertEqual(self.n.calls,[])
    def test_foreign_end_does_not_close_local(self):
        self.arm();self.event(True);self.event(False,Node(Class=self.s.cls));self.trend();self.assertEqual(len(self.n.calls),1)
    def test_wrong_skill_class(self):
        self.s.script.Class=Node(Name='other');self.arm();self.assertNotIn('skill_duration',self.m._automation_leases)
    def test_missing_event(self):
        self.s.funcs.remove(self.events[1]);self.arm();self.assertNotIn('skill_duration',self.m._automation_leases);self.trend();self.assertEqual(self.n.calls,[])
    def test_wrong_signature(self):
        self.events[0].NumParams=1;self.arm();self.assertNotIn('skill_duration',self.m._automation_leases)
    def test_missing_hook_after_arm(self):
        self.arm();self.event(True);self.s.b.hooks.pop(self.m._crossfire_hooks[1][1]);self.trend();self.assertEqual(self.n.calls,[])
    def test_end_during_getter(self):
        self.arm();self.event(True);self.s.advance(d=.75);self.s.advance(d=.70);l=self.m._automation_leases['skill_duration'];old=l.adaptive_api[0]
        def getter(*a):
            self.event(False);return old(*a)
        l.adaptive_api=(getter,l.adaptive_api[1]);self.s.advance(d=.65);self.assertEqual(self.n.calls,[])
    def test_join(self):
        self.arm();self.event(True);self.s.advance(d=.75);self.s.b.f.players=2;self.trend();self.assertEqual(self.n.calls,[])
    def test_mode_change(self):
        self.arm();self.event(True);self.m.apply({'crossfire_duration_events':False});self.trend();self.assertEqual(self.n.calls+self.s.calls,[]);self.assertNotIn('skill_duration',self.m._automation_leases)
    def test_follow_conflict(self):
        self.arm(follow_skill_duration=True);self.assertNotIn('skill_duration',self.m._automation_leases)
    def test_no_native_backend(self):
        self.n.a.arm('duration',crossfire_duration_events=True);self.trend();self.assertEqual(self.n.calls+self.s.calls,[])
    def test_duplicate_start_discards_trend(self):
        self.arm();self.event(True);self.s.advance(d=.75);self.s.advance(d=.70);self.event(True);self.s.advance(d=.65);self.assertEqual(self.n.calls,[])
    def test_f8_option_visible(self):
        self.m.auto_master.value=True;self.m._category=6;self.s.b.gui.imgui.labels=[];self.m.draw();o=self.m.CROSSFIRE_GATE;self.assertIn(o.display_name+'##'+o.identifier,self.s.b.gui.imgui.labels)
    def test_registration_partial_inert(self):
        orig=self.hooks.add_hook
        def add(p,k,t,cb):
            if t=='bl4_custom_crossfire_r60_1':return False
            return orig(p,k,t,cb)
        self.hooks.add_hook=add;self.arm();self.assertIsNone(self.m._crossfire_hooks);self.assertNotIn('skill_duration',self.m._automation_leases);self.trend();self.assertEqual(self.n.calls,[])
    def test_depleted_without_end_event(self):
        self.arm();self.event(True);self.s.advance(d=.75);self.s.advance(d=.04);self.trend();self.assertEqual(self.n.calls,[])
    def test_upward_reset_without_event(self):
        self.arm();self.event(True);self.s.advance(d=.55);self.s.advance(d=.85);self.trend();self.assertEqual(self.n.calls,[])
    def test_end_during_final_getter(self):
        self.arm();self.event(True);self.s.advance(d=.75);self.s.advance(d=.70);l=self.m._automation_leases['skill_duration'];old=l.adaptive_api[0];count=[0]
        def getter(*a):
            count[0]+=1
            if count[0]==2:self.event(False)
            return old(*a)
        l.adaptive_api=(getter,l.adaptive_api[1]);self.s.advance(d=.65);self.assertEqual(self.n.calls,[])
    def test_end_during_dispatch_no_further_refill(self):
        def effect(i,a):self.s.val[i]+=a;self.event(False)
        self.n.effect=effect;self.arm();self.event(True);self.trend();self.assertEqual(len(self.n.calls),1);self.s.advance(d=.6);self.s.advance(d=.55);self.assertEqual(len(self.n.calls),1)
