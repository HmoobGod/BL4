"""Continuous reload experiment, isolated synthetic fixtures."""
import unittest
from test_reload_r20 import ReloadTests

class Continuous(unittest.TestCase):
    def setUp(self):
        self.r=ReloadTests();self.r.setUp();self.addCleanup(self.r.doCleanups)
        self.r.m.activate_feature('reload_continuous',1.);self.r.m.monitor_tick()
    def completion(self):
        r=self.r;r.advance(state='Reloading');r.advance(8,state='Active');r.advance(8,state='Active')
    def test_two_cycles(self):
        r=self.r;r.empty();self.assertEqual(len(r.calls),1);self.completion();r.empty();self.assertEqual(len(r.calls),2)
    def test_no_duplicate_empty(self):
        r=self.r;r.empty();r.advance();r.advance();r.advance();self.assertEqual(len(r.calls),1)
    def test_no_completion_timeout(self):
        r=self.r;r.empty();r.advance(dt=10.1);self.assertFalse(r.m.health_active());self.assertEqual(len(r.calls),1)
    def test_positive_without_reload_state(self):
        r=self.r;r.empty();r.advance(8);r.empty();self.assertFalse(r.m.health_active());self.assertEqual(len(r.calls),1)
    def test_interrupted(self):
        r=self.r;r.empty();r.advance(state='Reloading');r.advance(state='Firing');r.empty();self.assertEqual(len(r.calls),1);self.assertFalse(r.m.health_active())
    def test_join_waiting(self):
        r=self.r;r.empty();r.b.f.players=2;self.completion();r.empty();self.assertEqual(len(r.calls),1)
    def test_stop_waiting(self):
        r=self.r;r.empty();r.m.request_stop('owner');self.completion();r.empty();self.assertEqual(len(r.calls),1)
    def test_expiry(self):
        r=self.r;r.empty();self.completion();r.advance(dt=30);r.empty();self.assertEqual(len(r.calls),1)
    def test_two_positive_samples(self):
        r=self.r;r.empty();r.advance(state='Reloading');r.advance(8,state='Active');r.empty();self.assertEqual(len(r.calls),1)
    def test_mode_change(self):
        r=self.r;r.empty();r.w.CurrentUseModeIndex=1;self.completion();r.empty();self.assertEqual(len(r.calls),1)
    def test_request_limit(self):
        r=self.r
        for i in range(10):
            r.empty();self.assertEqual(len(r.calls),i+1)
            if i<9:self.completion()
        self.assertFalse(r.m.health_active());self.completion();r.empty();self.assertEqual(len(r.calls),10)
    def test_dispatch_fault(self):
        r=self.r
        def fail(*a):raise RuntimeError('uncertain')
        fail.func=r.fn;r.w.ServerStartReloading=fail;r.empty();self.assertTrue(r.m.health_fault());self.assertFalse(r.m.health_active())
    def test_conflict_during_wait(self):
        import sys
        from types import SimpleNamespace as N
        r=self.r;r.empty()
        self.addCleanup(sys.modules.pop,'auto_reload',None)
        sys.modules['auto_reload']=N(mod=N(is_enabled=True))
        self.completion();r.empty();self.assertEqual(len(r.calls),1);self.assertFalse(r.m.health_active())
