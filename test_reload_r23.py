"""Independent immediate native reload witness, no additional dispatch."""
import unittest
from test_reload_r20 import ReloadTests

class FastReload(unittest.TestCase):
    def setUp(self):
        self.r=ReloadTests();self.r.setUp();self.addCleanup(self.r.doCleanups)
    def start(self,callback):
        r=self.r
        def request(*a):
            r.calls.append(a);callback()
        request.func=r.fn;r.w.ServerStartReloading=request
        r.m.activate_feature('reload_continuous',1.);r.m.monitor_tick()
    def test_fast_native_reload(self):
        r=self.r;self.start(lambda:setattr(r.w,'CurrentState','Reloading'));r.empty()
        self.assertTrue(r.m._health_pulse.saw_reload)
        r.advance(8,state='Active');r.advance(8,state='Active');r.empty();self.assertEqual(len(r.calls),2)
    def test_no_start_witness(self):
        r=self.r;self.start(lambda:None);r.empty();r.advance(8);r.empty();self.assertEqual(len(r.calls),1);self.assertFalse(r.m.health_active())
    def test_immediate_unexpected_state(self):
        r=self.r;self.start(lambda:setattr(r.w,'CurrentState','Firing'));r.empty();self.assertFalse(r.m.health_active());self.assertEqual(len(r.calls),1)
    def test_immediate_scope_change(self):
        r=self.r;self.start(lambda:setattr(r.w,'CurrentUseModeIndex',1));r.empty();self.assertFalse(r.m.health_active());self.assertFalse(r.m.health_fault());self.assertEqual(len(r.calls),1)
    def test_immediate_stop(self):
        r=self.r;self.start(lambda:r.m.request_stop('owner'));r.empty();self.assertFalse(r.m.health_active());self.assertEqual(len(r.calls),1)
    def test_immediate_ammo_without_state(self):
        r=self.r
        def gain():r.loaded=r.pool.LoadedAmmo=r.pool.ServerSyncedLoadedAmmo=8
        self.start(gain);r.empty();self.assertFalse(r.m.health_active());self.assertEqual(len(r.calls),1)
    def test_rearm_resets_completed(self):
        r=self.r;self.start(lambda:setattr(r.w,'CurrentState','Reloading'));r.empty();a=r.m._health_pulse;a.stop('test');r.advance(8,state='Active');self.assertTrue(a.begin());self.assertEqual(a.completed,0);self.assertFalse(a.waiting);self.assertFalse(a.saw_reload)
