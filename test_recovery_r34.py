"""Continuous recovery lane integration: synthetic native call fixtures only."""
import unittest
from types import SimpleNamespace as N
from test_health_pulse_r17 import HealthPulse
from test_combat_r13 import attr
from test_automation_r27 import Lane

class ContinuousRecovery(unittest.TestCase):
    def setUp(self):
        h=HealthPulse();h.setUp();self.addCleanup(h.doCleanups);self.h=h;self.m=h.m
        self.shield=attr(50.);self.shield._type=h.cur._type
        h.shield.SimpleCurrentHealth=self.shield;h.shield.SimpleMaxHealth=h.max
        self.calls=[]
        def layer(p,k,top):
            self.assertIs(p,h.p);self.assertIs(top,False);return 1 if k is h.hp else 0
        def percent(p,idx):return (h.cur if idx==1 else self.shield).Value/100.
        def refill(p,k,amount,cap):
            self.assertIs(p,h.p);self.assertEqual(cap,1.);self.assertGreater(amount,0);self.assertLessEqual(amount,.01)
            a=h.cur if k is h.hp else self.shield;self.calls.append(('health' if k is h.hp else 'shield',amount));a._values['Value']=min(100.,a.Value+amount*100)
        for f,call in zip(h.funcs,(layer,percent,refill),strict=True):
            def bound(*a,call=call):return call(*a)
            bound.func=f;setattr(f.Outer.ClassDefaultObject,f.Name,bound)
        self.factory=self.m.make_automation_lane
    def tick(self,n=1,dt=1.):
        for _ in range(n):self.h.advance(dt)
    def arm(self,*kinds,**settings):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**{'persistent_automation_'+k:True for k in kinds},**settings});self.tick(4,dt=.3)
    def test_default_off(self):
        self.arm();self.tick(4);self.assertFalse(self.m._automation_leases);self.assertEqual(self.calls,[])
    def test_continuous_after_30_seconds(self):
        self.arm('health');self.tick(dt=31.);self.assertEqual(self.calls,[('health',.01)]);self.tick();self.assertEqual(len(self.calls),2);self.assertIn('health',self.m._automation_leases)
    def test_shield_only_rising(self):
        self.arm('shield');self.tick();self.shield._values['Value']=55.;self.tick();self.assertEqual(self.calls,[]);self.shield._values['Value']=60.;self.tick();self.assertEqual(self.calls,[('shield',.01)]);self.tick();self.assertEqual(len(self.calls),1)
    def test_both_lanes_and_movement(self):
        self.arm('health','shield',persistent_jump=True,jump=1.5);self.shield._values['Value']=55.;self.tick();self.shield._values['Value']=60.;self.tick();self.assertIn(('shield',.01),self.calls);self.assertIn(('health',.01),self.calls);self.assertIn('jump',self.m._controller.records)
    def test_independent_disable(self):
        self.arm('health','shield');self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['health'],False);self.calls.clear();self.shield._values['Value']=55.;self.tick();self.shield._values['Value']=60.;self.tick();self.assertEqual(self.calls,[('shield',.01)]);self.assertNotIn('health',self.m._automation_leases)
    def test_master_off(self):
        self.arm('health','shield');self.m.set_auto_setting(self.m.auto_master,False);self.calls.clear();self.tick(2);self.assertEqual(self.calls,[]);self.assertFalse(self.m._automation_leases)
    def test_join_stops(self):
        self.arm('health');self.calls.clear();self.h.b.f.players=2;self.tick();self.assertEqual(self.calls,[]);self.assertNotIn('health',self.m._automation_leases)
    def test_no_effect_no_retry(self):
        self.arm('health');lease=self.m._automation_leases['health'];lease.api=(*lease.api[:2],lambda *a:None);self.tick(3);self.assertNotIn('health',self.m._automation_leases);self.tick(3);self.assertNotIn('health',self.m._automation_leases)
    def test_healing_multiplier_stops_only_recovery(self):
        # Use selected multiplier for admission check even if field unavailable; no need to write it.
        self.m.make_automation_lane=lambda k,s:Lane(k,self.m) if k=='reload' else self.factory(k,s)
        self.arm('health','reload');self.m.apply({'persistent_healing_received':True,'healing_received':2.});self.m.automation_tick();self.assertNotIn('health',self.m._automation_leases);self.assertIn('reload',self.m._automation_leases)
    def test_fault_stops_peer(self):
        self.arm('health','shield');lease=self.m._automation_leases['health'];lease.api=(*lease.api[:2],lambda *a:(_ for _ in ()).throw(RuntimeError('uncertain')));self.tick();self.assertTrue(self.m.automation_fault());self.assertNotIn('shield',self.m._automation_leases)
    def test_reentrant_disable_after_read(self):
        self.arm('health');lease=self.m._automation_leases['health'];original=lease.api[1]
        def read(*a):
            result=original(*a);self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['health'],False);return result
        lease.api=(lease.api[0],read,lease.api[2]);self.calls.clear();self.tick();self.assertEqual(self.calls,[])
    def test_full_waits_then_recovers(self):
        self.h.cur._values['Value']=100.;self.arm('health');self.tick(3);self.assertEqual(self.calls,[]);self.h.cur._values['Value']=90.;self.tick();self.assertEqual(self.calls,[('health',.01)])
