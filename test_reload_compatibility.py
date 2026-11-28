"""Synthetic compatibility tests for automatic reload weapon switching and native completion."""
import types
import unittest
from test_automation_r28 import SwapReload


class ReloadCompatibilityTests(SwapReload):
    def test_equipping_and_putting_down_are_benign_wait_states(self):
        self.r.w.CurrentState = 'PuttingDown'
        self.tick(state='PuttingDown')
        self.assertIsNotNone(self.a.record)
        self.assertTrue(self.a.swap_paused)
        self.assertFalse(self.r.calls)

        self.r.w.CurrentState = 'Equipping'
        self.tick(state='Equipping')
        self.assertIsNotNone(self.a.record)
        self.assertTrue(self.a.swap_paused)
        self.assertFalse(self.r.calls)

        # Returning to Active loaded weapon resumes cleanly
        self.r.w.CurrentState = 'Active'
        self.tick(4, 'Active')
        self.assertIsNotNone(self.a.record)
        self.assertFalse(self.a.swap_paused)
        self.tick(4, 'Active')
        self.empty()
        self.assertEqual(len(self.r.calls), 1)

    def test_unknown_transition_state_still_fails_closed(self):
        self.r.w.CurrentState = 'CorruptedUnknownState'
        self.tick(state='CorruptedUnknownState')
        self.assertIsNone(self.a.record)
        self.assertFalse(self.r.calls)

    def test_behavior_use_mode_index_parser(self):
        from bl4_custom_foundation.reload_assist import behavior_use_mode_index
        self.assertEqual(behavior_use_mode_index(types.SimpleNamespace(Name='UM0_5B')), 0)
        self.assertEqual(behavior_use_mode_index(types.SimpleNamespace(Name='UM1_AmmoPool')), 1)
        self.assertEqual(behavior_use_mode_index(types.SimpleNamespace(Name='UM12_Reload')), 12)
        self.assertIsNone(behavior_use_mode_index(types.SimpleNamespace(Name='WeaponBehavior_AmmoPool')))
        self.assertIsNone(behavior_use_mode_index(types.SimpleNamespace(Name='UM_NoDigits')))

    def test_native_on_reload_ended_observer_marks_pinned_weapon_only(self):
        from bl4_custom_foundation.reload_assist import ReloadCompletionObserver
        obs = ReloadCompletionObserver(self.a, self.a.thread)
        self.empty()
        self.assertTrue(self.a.waiting)
        self.a.saw_reload = False

        # Foreign weapon ignored
        foreign = types.SimpleNamespace(_get_address=lambda: 999999999)
        obs.on_reload_ended(None, types.SimpleNamespace(EventWeapon=foreign))
        self.assertFalse(self.a.saw_reload)
        self.assertEqual(obs.events, 0)

        # Wrong thread ignored
        wrong_obs = ReloadCompletionObserver(self.a, lambda: self.a.thread() + 1)
        wrong_obs.on_reload_ended(None, types.SimpleNamespace(EventWeapon=self.r.w))
        self.assertFalse(self.a.saw_reload)
        self.assertEqual(wrong_obs.events, 0)

        # Exact pinned weapon confirms native reload completion witness
        obs.on_reload_ended(None, types.SimpleNamespace(EventWeapon=self.r.w))
        self.assertTrue(self.a.saw_reload)
        self.assertEqual(obs.events, 1)

        # Two idle positive magazine samples complete the cycle without stopping
        self.tick(4, 'Active')
        self.tick(4, 'Active')
        self.assertFalse(self.a.waiting)
        self.assertIsNotNone(self.a.record)

    def test_opt_in_mid_reload_swap_recovery(self):
        from bl4_custom_foundation.reload_assist import ReloadAssist
        self.a = ReloadAssist(
            self.a.context, self.a.weak, self.a.api, self.a.fn,
            self.a.clock, self.a.thread, self.a.report,
            continuous=True, session_mode=True, recover_mid_reload_swap=True,
        )
        self.assertTrue(self.a.begin())
        self.empty()
        self.assertTrue(self.a.waiting)
        self.assertEqual(len(self.r.calls), 1)

        # Swap mid-reload: recovers instead of terminating session
        self.swap(loaded=4)
        self.tick(4, 'Active')
        self.assertIsNotNone(self.a.record)
        self.assertFalse(self.a.waiting)
        self.assertFalse(self.a.swap_paused)
        # Fresh weapon can now complete a normal reload cycle
        self.tick(4, 'Active')
        self.empty()
        self.assertEqual(len(self.r.calls), 2)


if __name__ == '__main__':
    unittest.main()
