"""Synthetic energy-shield assist; independent from natural recharge rate proof."""
import unittest
from types import SimpleNamespace as N
from test_health_pulse_r17 import HealthPulse, FGameDataHandle
from test_combat_r13 import attr, Node

class ShieldPulse(unittest.TestCase):
    def setUp(self):
        h=HealthPulse();h.setUp();self.addCleanup(h.doCleanups);self.h=h
        h.shield.SimpleCurrentHealth=attr(50.);h.shield.SimpleMaxHealth=attr(100.)
        self.cur=h.shield.SimpleCurrentHealth;self.max=h.shield.SimpleMaxHealth
        # Same reflected attribute wrappers as the original layer.
        self.cur._type=h.cur._type;self.max._type=h.max._type
        def layer(p,k,top):
            self.assertIs(p,h.p);self.assertIs(k,h.sh);self.assertIs(top,False);return 0
        def percent(p,idx):
            self.assertEqual(idx,0);return h.pct
        def refill(p,k,amount,cap):
            self.assertIs(p,h.p);self.assertIs(k,h.sh);self.assertEqual(cap,1.)
            h.calls.append(amount);self.value(min(1.,h.pct+amount))
        for f,call in zip(h.funcs,(layer,percent,refill),strict=True):
            def bound(*a,call=call):return call(*a)
            bound.func=f;setattr(f.Outer.ClassDefaultObject,f.Name,bound)
        self.calls=h.calls
    def value(self,p):self.h.pct=p;self.cur._values['Value']=p*100
    def start(self):self.h.m.activate_feature('shield_pulse',1.);self.h.m.monitor_tick()
    def tick(self,p=None,dt=1.):
        if p is not None:self.value(p)
        self.h.advance(dt)
    def rising(self):self.tick(.6);self.tick(.7)
    def test_two_rises_then_pulse(self):
        self.start();self.assertTrue(self.h.m.health_active());self.tick(.6);self.assertEqual(self.calls,[]);self.tick(.7);self.assertEqual(self.calls,[.01]);self.assertEqual(self.h.cur.Value,50.)
    def test_own_pulse_not_counted(self):
        self.start();self.rising();self.tick();self.tick(.72);self.assertEqual(self.calls,[.01]);self.tick(.73);self.assertEqual(self.calls,[.01,.01])
    def test_flat_or_falling_not_recharge(self):
        self.start();self.tick(.6);self.tick(.59);self.tick(.6);self.tick(.6);self.assertEqual(self.calls,[])
    def test_zero_waits(self):
        self.value(0.);self.start();self.assertTrue(self.h.m.health_active());self.tick();self.tick();self.assertEqual(self.calls,[]);self.tick(.01);self.tick(.02);self.assertEqual(self.calls,[.01])
    def test_full_no_refill(self):self.start();self.tick(.9);self.tick(1.);self.assertEqual(self.calls,[])
    def test_cap(self):self.start();self.tick(.98);self.tick(.997);self.assertAlmostEqual(self.calls[0],.003);self.assertEqual(self.h.pct,1.)
    def test_armor_excluded(self):self.h.sh.DisplayColor=N(name='ArmorYellow');self.start();self.assertFalse(self.h.m.health_active())
    def test_overshield_excluded(self):self.h.sh.Variation=N(name='IsOvershield');self.start();self.assertFalse(self.h.m.health_active())
    def test_duplicate_shield_rejected(self):self.h.p.HealthState.HealthTypeStates.append(self.h.shield);self.start();self.assertFalse(self.h.m.health_active())
    def test_switch_shield_rejected(self):self.start();self.tick(.6);self.h.sh._name='HealthType_Other';self.tick(.7);self.assertEqual(self.calls,[]);self.assertFalse(self.h.m.health_active())
    def test_join_before_pulse(self):self.start();self.tick(.6);self.h.b.f.players=2;self.tick(.7);self.assertEqual(self.calls,[]);self.assertFalse(self.h.m.health_active())
    def test_expiry(self):self.start();self.tick(.6,dt=29);self.tick(.7);self.assertEqual(self.calls,[]);self.assertFalse(self.h.m.health_active())
    def test_f8_queue(self):
        m=self.h.m;m._category=6;self.h.b.gui.imgui.clicks={'Start experimental shield assist (30 sec)'};m.draw();self.assertFalse(m.health_active());m.monitor_tick();self.assertTrue(m.health_active());self.rising();self.assertEqual(self.calls,[.01])
    def test_cannot_overlap_health(self):self.start();self.h.start();self.assertEqual(self.h.m._health_pulse.mode,'shield');self.rising();self.assertEqual(self.calls,[.01])
    def test_stop(self):self.start();self.tick(.6);self.h.m.request_stop('test');self.tick(.7);self.assertEqual(self.calls,[])
    def test_reject_stale_readback(self):self.start();self.tick(.6);self.h.pct=.7;self.h.advance();self.assertFalse(self.h.m.health_active());self.assertEqual(self.calls,[])
