"""Synthetic tests for separate outstanding reload request ownership across weapon swaps."""
import unittest
from test_reload_notifications import ReloadNotifications


class ReloadOutstandingSwapTests(ReloadNotifications):
    def setUp(self):
        super().setUp()
        self.a.track_outstanding_on_swap = True

    def restore_weapon(self, saved):
        self.r.w.CurrentState = 'Inactive'
        self.r.w, self.r.pool, slot_w = saved
        self.r.p.ActiveWeapons.Slots[0].Weapon = slot_w
        self.r.w.CurrentState = 'Active'

    def test_mid_reload_swap_parks_weapon_a_and_allows_weapon_b(self):
        saved_a = (self.r.w, self.r.pool, self.r.p.ActiveWeapons.Slots[0].Weapon)
        wid_a = saved_a[0]._get_address()
        self.empty()
        self.start_event(weapon=saved_a[0])
        self.assertTrue(self.a.waiting)
        self.assertEqual(len(self.r.calls), 1)

        # Swap to Weapon B mid-reload: Weapon A parked, Weapon B admitted cleanly
        self.swap(loaded=4)
        self.tick(4, 'Active')
        self.assertIsNotNone(self.a.record)
        self.assertIn(wid_a, self.a._outstanding)
        self.assertFalse(self.a.waiting)

        # Weapon B completes its own normal reload cycle
        self.tick(4, 'Active')
        self.empty()
        self.assertEqual(len(self.r.calls), 2)
        self.start_event()
        self.end_event(True)
        self.finish_fast()
        self.assertFalse(self.a.waiting)

        # Parked Weapon A receives paired OnReloadEnded(bCompleted=True) while stowed
        self.end_event(True, weapon=saved_a[0])
        self.assertTrue(self.a._outstanding[wid_a]['event_complete'])

        # Swap back to Weapon A: restores outstanding receipt (never blindly rearms)
        self.restore_weapon(saved_a)
        self.tick(8, 'Active')
        self.assertTrue(self.a.waiting)
        self.assertNotIn(wid_a, self.a._outstanding)
        # Two positive idle samples finish Weapon A's restored receipt
        self.finish_fast()
        self.assertFalse(self.a.waiting)
        self.assertIsNotNone(self.a.record)
        self.assertEqual(len(self.r.calls), 2)

    def test_parked_cancelled_reload_stops_on_return(self):
        saved_a = (self.r.w, self.r.pool, self.r.p.ActiveWeapons.Slots[0].Weapon)
        self.empty()
        self.start_event(weapon=saved_a[0])
        self.swap(loaded=4)
        self.tick(4, 'Active')
        # Native cancellation (bCompleted=False) on parked Weapon A
        self.end_event(False, weapon=saved_a[0])
        self.restore_weapon(saved_a)
        self.tick(4, 'Active')
        self.assertIsNone(self.a.record)

    def test_parked_expired_reload_stops_on_return(self):
        saved_a = (self.r.w, self.r.pool, self.r.p.ActiveWeapons.Slots[0].Weapon)
        self.empty()
        self.start_event(weapon=saved_a[0])
        self.swap(loaded=4)
        self.tick(4, 'Active')
        # Advance past 10s completion deadline while on Weapon B
        self.tick(4, 'Active', dt=11.0)
        self.restore_weapon(saved_a)
        self.tick(4, 'Active')
        self.assertIsNone(self.a.record)

    def test_return_without_completion_keeps_waiting_and_never_rearms(self):
        saved_a = (self.r.w, self.r.pool, self.r.p.ActiveWeapons.Slots[0].Weapon)
        self.empty()
        self.start_event(weapon=saved_a[0])
        self.swap(loaded=4)
        self.tick(4, 'Active')
        self.restore_weapon(saved_a)
        # Returning to Weapon A still at 0 loaded ammo restores waiting state; no duplicate request
        self.tick(0, 'Active')
        self.assertTrue(self.a.waiting)
        self.assertEqual(len(self.r.calls), 1)
        self.tick(0, 'Active')
        self.assertEqual(len(self.r.calls), 1)

    def park_a(self):
        saved=(self.r.w,self.r.pool,self.r.p.ActiveWeapons.Slots[0].Weapon)
        self.empty();self.start_event(weapon=saved[0]);self.swap(4);self.tick(4,'Active')
        return saved

    def test_parked_event_requires_current_solo_scope(self):
        saved=self.park_a();wid=saved[0]._get_address()
        self.r.b.f.players=2;self.end_event(True,weapon=saved[0])
        self.assertFalse(self.a._outstanding[wid]['event_complete'])
        self.assertTrue(self.a._outstanding[wid]['cancelled'])

    def test_parked_event_requires_original_mode(self):
        saved=self.park_a();wid=saved[0]._get_address()
        saved[0].CurrentUseModeIndex=1;self.end_event(True,weapon=saved[0])
        self.assertTrue(self.a._outstanding[wid]['cancelled'])

    def test_parked_hook_loss_stops_all_requests(self):
        self.park_a();self.a.event_live=lambda:False;self.tick(4,'Active')
        self.assertIsNone(self.a.record);self.assertFalse(self.a._outstanding)

    def test_duplicate_parked_completion_invalidates(self):
        saved=self.park_a();wid=saved[0]._get_address()
        self.end_event(True,weapon=saved[0]);self.end_event(False,weapon=saved[0])
        self.assertTrue(self.a._outstanding[wid]['cancelled'])
        self.restore_weapon(saved);self.tick(8,'Active');self.assertIsNone(self.a.record)

    def test_no_start_witness_does_not_park(self):
        self.empty();self.swap(4);self.tick(4,'Active')
        self.assertIsNone(self.a.record);self.assertFalse(self.a._outstanding)

    def test_factory_and_actual_callback_while_other_weapon_idle(self):
        self.a.stop('replace fixture');self.bind_observers();m=self.r.m
        self.a=m.make_automation_lane('reload',m.bound_session(self.r.b.f.sdk))
        self.assertTrue(self.a.track_outstanding_on_swap);self.assertTrue(self.a.begin())
        m._automation_leases['reload']=self.a;m.automation_permitted=lambda:True
        saved=self.park_a();wid=saved[0]._get_address()
        from test_combat_r13 import Node
        from bl4_custom_foundation.reload_assist import EVENT_OWNER
        hooks=self.r.b.hooks;tp=self.r.b.f.sdk.hooks.Type.POST
        hooks[(EVENT_OWNER+':OnReloadEnded',tp,'bl4_custom_reload_observe_OnReloadEnded')](self.collector,Node(EventWeapon=saved[0],bCompleted=True))
        self.assertTrue(self.a._outstanding[wid]['event_complete'])
        self.restore_weapon(saved);self.tick(8,'Active');self.finish_fast();self.assertFalse(self.a.waiting)
        self.assertEqual(len(self.r.calls),1)


if __name__ == '__main__':
    unittest.main()
