"""Synthetic persistent native life-steal controls; no live healing claim."""
import unittest
from types import SimpleNamespace
from test_recovery_r14 import Recovery, Node
from test_automation_r27 import Lane

class PersistentLife(unittest.TestCase):
    def setUp(self):
        self.r=Recovery(); self.r.setUp(); self.addCleanup(self.r.doCleanups)
        self.m=self.r.m; self.f=self.r.c.b.f; self.f.solo=True
        self.rate=self.r.life; self.pct=self.r.percent; self.cap=self.r.cap
        self.now=100.; self.m.time=SimpleNamespace(monotonic=lambda:self.now)
    def tick(self,n=1):
        for _ in range(n):
            self.now+=.3; self.m.monitor_tick()
    def arm(self,**v):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**v,**{'persistent_'+k:True for k in v}}); self.tick(5)
    def set(self,a,v):a._values.update(Value=v,BaseValue=v)
    def test_defaults(self):
        self.m.apply({'lifesteal_rate':2.,'lifesteal_fraction':2.});self.arm();self.assertFalse(self.rate.writes+self.pct.writes)
    def test_rate_cycle(self):
        self.arm(lifesteal_rate=2.);self.assertEqual(self.rate.Value,4.);self.m.apply({'lifesteal_rate':3.});self.tick();self.assertEqual(self.rate.Value,6.);self.m.apply({'lifesteal_rate':1.});self.tick();self.assertEqual(self.rate.Value,2.);self.assertFalse(self.pct.writes+self.cap.writes)
    def test_fraction_cycle(self):
        self.arm(lifesteal_fraction=2.);self.assertAlmostEqual(self.pct.Value,.2);self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertAlmostEqual(self.pct.Value,.1);self.assertFalse(self.rate.writes+self.cap.writes)
    def test_initial_zero_waits_other_feature(self):
        self.set(self.rate,0.);self.arm(lifesteal_rate=2.,jump=1.5);self.assertFalse(self.rate.writes);self.assertIn('jump',self.m._controller.records);self.assertFalse(self.m._auto_blocked);self.set(self.rate,2.);self.tick(3);self.assertEqual(self.rate.Value,4.)
    def test_conflict_no_write(self):
        self.arm(lifesteal_rate=2.,lifesteal_fraction=2.,jump=1.5);self.assertFalse(self.rate.writes+self.pct.writes);self.assertIn('jump',self.m._controller.records)
    def test_conflict_restores(self):
        self.arm(lifesteal_rate=2.);self.m.apply({'persistent_lifesteal_fraction':True,'lifesteal_fraction':2.});self.tick(2);self.assertEqual(self.rate.Value,2.);self.assertFalse(self.pct.writes);self.m.set_auto_setting(self.m.AUTO_OPTIONS['lifesteal_rate'],False);self.tick(2);self.assertAlmostEqual(self.pct.Value,.2)
    def test_peer_drift_restores(self):
        self.arm(lifesteal_rate=2.);self.set(self.pct,.2);self.tick();self.assertEqual(self.rate.Value,2.);self.assertTrue(self.m._auto_blocked);self.assertFalse(self.pct.writes)
    def test_cap_change_restores_fraction(self):
        self.arm(lifesteal_fraction=2.);self.set(self.cap,9.);self.tick();self.assertEqual(self.pct.Value,.1);self.assertTrue(self.m._auto_blocked)
    def test_join_restore(self):
        self.arm(lifesteal_rate=2.);self.f.players=2;self.tick();self.assertEqual(self.rate.Value,2.)
    def test_foreign_drift(self):
        self.arm(lifesteal_rate=2.);self.rate._values['Value']=5.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.rate.Value,5.)
    def test_cap_wait(self):
        self.set(self.cap,3.);self.arm(lifesteal_rate=2.);self.assertFalse(self.rate.writes);self.assertFalse(self.m._auto_blocked)
    def test_unequal_peer(self):
        self.pct._values['Value']=.2;self.arm(lifesteal_rate=2.);self.assertFalse(self.rate.writes)
    def test_alias(self):
        self.r.damage.lifestealratecap=self.rate;self.arm(lifesteal_rate=.5);self.assertFalse(self.rate.writes)
    def test_partial_rollback(self):
        self.rate.raise_after='BaseValue';self.arm(lifesteal_rate=2.);self.assertEqual(self.rate.Value,2.);self.assertEqual(self.rate.BaseValue,2.)
    def test_flesh_conflict_other_automation_allowed(self):
        self.arm(lifesteal_rate=2.);self.assertTrue(self.m.automation_permitted());self.assertIn('life-steal',self.m.recovery_conflict('health'));self.assertEqual(self.m.recovery_conflict('shield'),'')
    def test_zero_fraction_waits(self):
        self.set(self.pct,0.);self.arm(lifesteal_fraction=2.);self.assertFalse(self.pct.writes);self.assertFalse(self.m._auto_blocked)
