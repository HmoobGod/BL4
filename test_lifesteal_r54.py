"""Synthetic independent native life-steal fraction controls; not gameplay proof."""
import unittest
from test_recovery_r14 import Recovery, Node

class LifeFraction(unittest.TestCase):
    def setUp(self):
        self.r=Recovery(); self.r.setUp(); self.addCleanup(self.r.doCleanups)
        self.m=self.r.m; self.p=self.r.percent; self.rate=self.r.life; self.cap=self.r.cap
    def apply(self,v):self.r.activate('lifesteal_fraction',v)
    def set(self,obj,v):obj._values.update(Value=v,BaseValue=v)
    def test_neutral(self):self.apply(1.);self.assertEqual(self.p.writes,[])
    def test_default_manual(self):
        self.assertNotIn('lifesteal_fraction',self.m.AUTO_OPTIONS)
        self.assertEqual(self.m._PREVIEW_BY_KEY['lifesteal_fraction'].value,1.)
        self.assertEqual(self.p.writes,[])
    def test_scale_update_restore(self):
        self.apply(2.);self.assertAlmostEqual(self.p.Value,.2);self.assertAlmostEqual(self.p.BaseValue,.2)
        self.apply(3.);self.assertAlmostEqual(self.p.Value,.3)
        self.apply(1.);self.assertEqual((self.p.Value,self.p.BaseValue),(.1,.1));self.assertEqual(self.rate.writes+self.cap.writes,[])
    def test_reduce(self):self.apply(.5);self.assertAlmostEqual(self.p.Value,.05)
    def test_zero(self):self.set(self.p,0.);self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_no_seed_rate(self):self.set(self.rate,0.);self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_no_seed_cap(self):self.set(self.cap,0.);self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_fraction_baseline(self):self.set(self.p,1.2);self.apply(.5);self.assertEqual(self.p.writes,[])
    def test_fraction_target(self):self.set(self.p,.75);self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_cap_bound(self):self.set(self.cap,1.);self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_rate_mismatch(self):self.rate._values['Value']=3.;self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_wrong_owner(self):self.r.damage.owner=Node();self.apply(2.);self.assertEqual(self.p.writes,[])
    def test_rate_drift_restores(self):
        self.apply(2.);self.set(self.rate,3.);self.m.monitor_tick();self.assertEqual(self.p.Value,.1);self.assertFalse(self.m._controller.records)
    def test_cap_loss_restores(self):
        self.apply(2.);self.set(self.cap,0.);self.m.monitor_tick();self.assertEqual(self.p.Value,.1);self.assertFalse(self.m._controller.records)
    def test_exclusive_rate_first(self):
        self.r.activate('lifesteal_rate',2.);self.apply(2.);self.assertEqual(self.p.writes,[]);self.assertEqual(self.rate.Value,4.)
    def test_exclusive_fraction_first(self):
        self.apply(2.);self.r.activate('lifesteal_rate',2.);self.assertEqual(self.rate.writes,[]);self.assertAlmostEqual(self.p.Value,.2)
    def test_post_write_failure_rolls_back(self):
        self.p.raise_after='Value';self.apply(2.);self.assertEqual((self.p.Value,self.p.BaseValue),(.1,.1));self.assertFalse(self.m._controller.records)
    def test_master_stop(self):
        self.apply(2.);self.m.request_stop('test',immediate=True);self.assertEqual(self.p.Value,.1)
