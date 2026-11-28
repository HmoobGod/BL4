"""Synthetic session Eridium formula-witnessed tests, not native gameplay certification."""
import unittest
from test_blackboard_rewards import RewardTests
from test_combat_r13 import Node
from test_double_jump_r52 import p, t
from test_native_resource_rates import FGbxDefPtr, WrappedStruct
from test_f8_simple import SimpleF8


class EridiumFormulaTests(RewardTests):
    def setUp(self):
        super().setUp()
        R = self.R
        self.eridium = R.TARGETS['progress_eridium']
        self.cash = R.TARGETS['progress_money']
        self.cash_generic = R.CASH_GENERIC
        self.values[self.cash_generic] = ('Float', 1.5)
        self.values[self.eridium] = ('Float', 1.0)
        self.defs.definitions[self.cash_generic] = Node(
            Context=Node(_type=self.ctx),
            Value=Node(_type=self.val, Variable=self.key(self.cash_generic)),
        )
        et = t('GbxAttributeExpression', R.ENGINE + 'GbxAttributeExpression')
        resolver = t('GbxExpressionValueResolver', R.ENGINE + 'GbxExpressionValueResolver', p('Expression', R.S, Struct=et))
        actor = t('ActorContextResolver', R.ENGINE + 'ActorContextResolver')
        self.formula_def = Node(Context=Node(_type=actor), Value=Node(_type=resolver, Expression=Node(_type=et)))
        self.defs.definitions[R.ERIDIUM_FORMULA] = self.formula_def
        self.formula_override = None

    def eridium_binding(self):
        R = self.R
        b = R.EridiumFormulaBinding(
            self.fs, self.bound, lambda typ, Name: self.key(Name), FGbxDefPtr, self.defs, WrappedStruct
        )
        original = b.calls['GetValueOfAttribute']

        def read(k, owner, default):
            if k == R.ERIDIUM_FORMULA:
                if self.formula_override is not None:
                    return self.formula_override
                return 1.0 * self.values[self.eridium][1]
            if k == self.cash_generic:
                return self.values[self.cash_generic][1]
            return original(k, owner, default)

        b.calls['GetValueOfAttribute'] = read
        return b

    def trial(self, scale=2.5, continuous=True):
        cls = self.R.SessionEridiumTrial if continuous else self.R.EridiumFormulaTrial
        return cls(
            'progress_eridium', scale, self.eridium_binding(),
            lambda: (self.pc, self.pawn, self.state, self.ok),
            lambda o: (lambda: o), lambda: self.time, lambda: self.tid,
            self.messages.append, lambda: self.permission
        )

    def test_session_lifetime_decimal_precision_and_restore(self):
        l = self.trial(scale=2.3, continuous=True)
        self.assertTrue(l.begin(), self.messages)
        self.tick(l)
        self.tick(l, 100.)
        self.assertEqual(l.phase, 'active')
        self.assertAlmostEqual(self.values[self.eridium][1], 2.3, places=6)
        self.assertEqual(self.values[self.cash][1], 2.0)
        self.assertEqual(self.values[self.cash_generic][1], 1.5)
        l.stop('off')
        self.tick(l)
        self.tick(l)
        self.assertEqual(l.phase, 'done')
        self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)
        self.assertEqual(len(self.calls), 2)

    def test_max_scale_10x_and_min_step_1_1x(self):
        for scale in (1.1, 10.0):
            self.calls.clear()
            self.values[self.eridium] = ('Float', 1.0)
            l = self.trial(scale=scale, continuous=True)
            self.assertTrue(l.begin(), self.messages)
            self.tick(l)
            self.assertEqual(l.phase, 'active')
            self.assertAlmostEqual(self.values[self.eridium][1], scale, places=6)
            l.stop('off')
            self.tick(l)
            self.tick(l)
            self.assertEqual(l.phase, 'done')
            self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)

    def test_session_requires_calc_eridium_pickup_formula(self):
        del self.defs.definitions[self.R.ERIDIUM_FORMULA]
        l = self.trial(scale=2.0, continuous=True)
        self.assertFalse(l.begin())
        self.assertFalse(self.calls)

    def test_manual_trial_allows_formula_absent_fallback(self):
        del self.defs.definitions[self.R.ERIDIUM_FORMULA]
        l = self.trial(scale=2.0, continuous=False)
        self.assertTrue(l.begin(), self.messages)
        self.tick(l)
        self.assertEqual(l.phase, 'active')
        self.assertAlmostEqual(self.values[self.eridium][1], 2.0, places=6)
        l.stop('off')
        self.tick(l)
        self.tick(l)
        self.assertEqual(l.phase, 'done')
        self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)

    def test_formula_drift_triggers_fault_and_restores(self):
        l = self.trial(scale=3.0, continuous=True)
        self.assertTrue(l.begin(), self.messages)
        self.tick(l)
        self.formula_override = 99.0
        self.tick(l)
        self.assertTrue(l.fault)
        self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)

    def test_cash_peer_isolation(self):
        l = self.trial(scale=2.0, continuous=True)
        self.assertTrue(l.begin(), self.messages)
        self.tick(l)
        self.values[self.cash_generic] = ('Float', 9.0)
        self.tick(l)
        self.assertTrue(l.fault)
        self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)

    def test_eligibility_loss_cleans_up(self):
        l = self.trial(scale=2.0, continuous=True)
        self.assertTrue(l.begin(), self.messages)
        self.tick(l)
        self.ok = False
        self.permission = False
        self.tick(l, permit=False)
        self.tick(l, permit=False)
        self.assertEqual(l.phase, 'done')
        self.assertAlmostEqual(self.values[self.eridium][1], 1.0, places=6)

    def test_no_implicit_rearm_and_cash_exclusion(self):
        m = self.base.m
        k = m.ERIDIUM_LANE
        o = m._PREVIEW_BY_KEY['progress_eridium']
        self.assertIs(m.NATIVE_RATE_OPTIONS['eridium'], o)
        self.assertEqual(sum(x is o for x in m.ALL), 1)
        self.assertIn(o, m._COMPACT_OPTIONS[1])
        self.assertFalse(m.NATIVE_AUTO_OPTIONS[k].value)
        m.NATIVE_AUTO_OPTIONS[k].value = True
        o.value = 2.5
        self.assertTrue(m.native_rate_allowed(k, 2.5))
        # Mutually exclusive with cash session
        m.NATIVE_AUTO_OPTIONS[m.CASH_LANE].value = True
        m._PREVIEW_BY_KEY['progress_money'].value = 2.0
        self.assertFalse(m.native_rate_allowed(k, 2.5))
        m.NATIVE_AUTO_OPTIONS[m.CASH_LANE].value = False
        self.assertTrue(m.native_rate_allowed(k, 2.5))
        l = self.trial(scale=2.5, continuous=True)
        l.begin()
        self.tick(l)
        orig = l.record
        l.stop('edit')
        self.tick(l)
        self.tick(l)
        self.assertFalse(l.rearm_verified(orig, 3.0))


class SessionEridiumUI(SimpleF8):
    def test_eridium_compact_and_toggle(self):
        m = self.m
        m._category = 1
        m._compact_view = True
        f = m.NATIVE_AUTO_OPTIONS['native_rate_eridium']
        label = f.display_name + '##' + f.identifier
        labels = self.render()
        self.assertIn(label, labels)
        self.assertIn('Eridium##progress_eridium', labels)
        self.assertTrue(any('Test earned Eridium' in x for x in labels))
        self.render({'Eridium##progress_eridium': 2.5, label: True})
        self.assertTrue(m.auto_master.value)
        self.assertTrue(f.value)
        self.assertEqual(m._PREVIEW_BY_KEY['progress_eridium'].value, 2.5)
        self.render(clicks=['Restore All'])
        self.assertFalse(f.value)
        self.assertFalse(m.auto_master.value)

    def test_eridium_factory_route(self):
        m = self.m
        m._PREVIEW_BY_KEY['progress_eridium'].value = 3.2
        seen = []
        m.make_session_eridium = lambda session, selection: seen.append((session, selection)) or 'eridium'
        self.assertEqual(m.make_automation_lane('native_rate_eridium', 'session'), 'eridium')
        self.assertEqual(seen, [('session', 3.2)])


if __name__ == '__main__':
    unittest.main()
