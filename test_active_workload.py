import unittest
from types import SimpleNamespace as N
from test_r3_persistent import Persistent
from test_automation_r27 import Automation
from test_batch import Attr

class ActiveWorkload(unittest.TestCase):
    def setUp(self):
        self.p=Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.m=self.p.m;self.now=100.;self.m.time=N(monotonic=lambda:self.now)
    def tick(self,dt=.3):
        self.now+=dt;self.p.tick()
    def test_pair_scans_once_on_each_active_camera(self):
        self.p.configure(repair_cooldown=.5);self.tick()
        a=self.p.b.cool;original=a._type._properties;calls=[]
        a._type._properties=lambda:(calls.append(1),original())[1]
        self.tick();self.tick();self.assertEqual(len(calls),2)
        self.assertEqual(a.Value,10.)
    def test_pair_duplicate_reflection_rejected(self):
        from bl4_custom_foundation.gameplay_fields import pair
        a=Attr(2.);old=a._type._properties;a._type._properties=lambda:old()+old()[:1]
        with self.assertRaises(ValueError):pair(a)
    def test_pair_zero_only_explicit(self):
        from bl4_custom_foundation.gameplay_fields import pair
        a=Attr(0.)
        with self.assertRaises(ValueError):pair(a)
        self.assertEqual(tuple(f[3] for f in pair(a,allow_zero=True)),(0.,0.))
    def test_pair_reads_live_value_and_base(self):
        from bl4_custom_foundation.gameplay_fields import pair
        a=Attr(1.);self.assertEqual(tuple(f[3] for f in pair(a)),(1.,1.))
        a.BaseValue=2.;self.assertEqual(tuple(f[3] for f in pair(a)),(1.,2.))
    def test_ground_missing_component_does_not_restore_peer(self):
        self.p.configure(walk_speed=2.,legendary_weight=3.);self.tick();self.tick()
        c=self.m._controller;old=c.capture
        def capture(key):
            if key=='walk_speed':raise ValueError('component temporarily unavailable')
            return old(key)
        c.capture=capture;self.m.ground_tick(self.p.anim)
        self.assertFalse(self.m._auto_blocked);self.assertEqual(self.p.f.weight,3.)
        self.tick();self.assertIsNone(self.m._auto_ground)
        c.capture=old;self.tick(1.1);self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.);self.assertEqual(self.p.f.weight,3.)
    def test_stopped_lane_skips_permission_recheck_but_live_lane_checks(self):
        a=Automation();a.setUp();self.addCleanup(a.doCleanups);a.arm()
        m=a.m;v=a.lanes['vacuum'];v.record=None;a.tick();self.assertNotIn('vacuum',m._automation_leases)
        orig=m.automation_permitted;calls=[]
        m.automation_permitted=lambda:(calls.append(1),orig())[1]
        before=a.lanes['reload'].ticks;a.tick()
        self.assertEqual(len(calls),3);self.assertEqual(a.lanes['reload'].ticks,before+1)
