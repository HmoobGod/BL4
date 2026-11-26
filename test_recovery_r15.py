"""Synthetic swap-field and offline native lease lifetime regressions."""
import unittest
from test_combat_r13 import Combat, Node, attr, desc


class Swap(unittest.TestCase):
    def setUp(self):
        self.c = Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.p, self.m = self.c.p, self.c.m
        self.p._path_name = lambda: 'player_instance'
        self.a = attr(1.)
        self.p.WeaponSwapTimeScale = self.a
        prior = self.p.Class._properties()
        self.p.Class._properties = lambda: prior + [desc('WeaponSwapTimeScale', self.a._type)]

    def test_cycle(self):
        self.c.activate('swap_time', 2.); self.assertEqual(self.c.vals(self.a), (2., 2.))
        self.c.activate('swap_time', .5); self.assertEqual(self.c.vals(self.a), (.5, .5))
        self.c.activate('swap_time', 1.); self.assertEqual(self.c.vals(self.a), (1., 1.))

    def test_manual(self):
        self.assertNotIn('swap_time', self.m.AUTO_OPTIONS)
        self.assertEqual(self.a.writes, [])

    def test_default_refused(self):
        self.p._path_name = lambda: 'Default__Player'
        self.c.activate('swap_time', 2.); self.assertEqual(self.a.writes, [])

    def test_descriptor_refused(self):
        self.p.Class._properties = lambda: []
        self.c.activate('swap_time', 2.); self.assertEqual(self.a.writes, [])

    def test_foreign_drift(self):
        self.c.activate('swap_time', 2.); self.a._values['Value'] = 3.
        self.m.monitor_tick(); self.assertTrue(self.m._controller.fault)
        self.assertEqual(self.a.Value, 3.)

    def test_join_restore(self):
        self.c.activate('swap_time', 2.); self.c.b.f.players = 2
        self.m.monitor_tick(); self.assertEqual(self.c.vals(self.a), (1., 1.))




class Lease(unittest.TestCase):
    def setUp(self):
        from native_regen_lease import Lease as NativeLease
        self.calls = []; self.p = object(); self.rate = object(); self.tags = object()
        self.l = NativeLease(lambda: (self.p, 'old', self.rate, self.tags), self.start, self.stop, lambda h: h == 7)

    def start(self, *args):
        self.calls.append(('start', args)); return 7

    def stop(self, *args):
        self.calls.append(('stop', args))

    def test_exact_bounded_call(self):
        self.assertTrue(self.l.begin(5, .25)); self.assertEqual(self.calls, [('start', (self.p, 5, self.rate, True, .25, self.tags))])
        self.assertFalse(self.l.begin(5, .25)); self.assertTrue(self.l.cancel(lambda: (self.p, 'old')))
        self.assertEqual(self.calls[-1], ('stop', (self.p, 7))); self.assertTrue(self.l.cancel(lambda: None))

    def test_invalid_input(self):
        for duration, tick in [(6,.25), (float('nan'),.25), (1,0), (.1,.25), (True,.25)]:
            self.assertFalse(self.l.begin(duration,tick))
        self.assertEqual(self.calls, [])

    def test_admission_missing(self):
        self.l.admit = lambda: None
        self.assertFalse(self.l.begin(1,.5)); self.assertEqual(self.calls, [])

    def test_bad_native_id(self):
        self.l.start = lambda *a: -1
        self.assertFalse(self.l.begin(1,.5)); self.assertTrue(self.l.fault)
        self.assertFalse(self.l.begin(1,.5))

    def test_no_replacement_stop(self):
        self.assertTrue(self.l.begin(1,.5)); self.assertFalse(self.l.cancel(lambda: (object(),'new')))
        self.assertTrue(self.l.fault); self.assertEqual(len(self.calls),1)

    def test_uncertain_start(self):
        def error(*args): raise RuntimeError('unknown native dispatch')
        self.l.start = error; self.assertFalse(self.l.begin(1,.5)); self.assertTrue(self.l.fault)

    def test_stop_failure(self):
        self.assertTrue(self.l.begin(1,.5))
        def error(*args): raise RuntimeError('unknown native dispatch')
        self.l.stop = error; self.assertFalse(self.l.cancel(lambda: (self.p,'old')))
        self.assertTrue(self.l.fault); self.assertIsNotNone(self.l.record)
