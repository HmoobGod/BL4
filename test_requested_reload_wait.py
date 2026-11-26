"""Session-only readiness waits: genuine depletion required after every wait."""
from test_automation_r28 import SwapReload
from test_combat_r13 import Node

class ReloadWait(SwapReload):
    def restart(self):
        self.a.stop('test rearm');self.assertTrue(self.a.begin());self.assertTrue(self.a.swap_paused)
    def resume(self):
        self.tick(4,'Active');self.assertFalse(self.a.swap_paused);self.assertIsNone(self.a.previous)
        self.tick();self.assertEqual(self.a.previous,4);self.assertFalse(self.r.calls)
        self.empty();self.assertEqual(self.r.calls,[(0,0)])
    def test_initial_empty(self):
        self.tick(0);self.restart();self.tick();self.tick();self.assertFalse(self.r.calls);self.resume()
    def test_initial_no_reserve(self):
        self.r.pool.StoredAmmo=self.r.pool.SpareAmmo=0;self.restart();self.tick();self.r.pool.StoredAmmo=self.r.pool.SpareAmmo=20;self.resume()
    def test_initial_busy(self):
        self.tick(state='Firing');self.restart();self.tick();self.resume()
    def test_initial_no_active(self):
        self.r.w.CurrentState='Inactive';self.restart();self.assertEqual(len(self.a.record[0]),3);self.tick();self.resume()
    def test_initial_pending(self):
        slot=self.r.p.ActiveWeapons.Slots[0];slot.PendingWeapon=self.r.w;self.restart();self.tick();slot.PendingWeapon=None;self.resume()
    def test_initial_empty_slots(self):
        slot=self.r.p.ActiveWeapons.Slots[0];slot.Weapon=None;self.restart();self.tick();slot.Weapon=self.r.w;self.resume()
    def test_empty_replacement(self):
        self.tick(0,'Firing');self.swap(0);self.tick();self.assertTrue(self.a.swap_paused);self.tick();self.assertFalse(self.r.calls);self.resume()
    def test_no_reserve_replacement(self):
        self.swap();self.r.pool.StoredAmmo=self.r.pool.SpareAmmo=0;self.tick();self.assertTrue(self.a.swap_paused);self.tick();self.r.pool.StoredAmmo=self.r.pool.SpareAmmo=20;self.resume()
    def test_busy_replacement(self):
        self.swap();self.tick(state='Reloading');self.assertTrue(self.a.swap_paused);self.tick();self.resume()
    def test_depletion_during_wait_does_not_trigger(self):
        self.swap(0);self.tick();self.tick(4,'Active');self.tick(0,'Firing');self.tick(state='Active');self.assertFalse(self.r.calls);self.tick(4,'Active');self.empty();self.assertEqual(len(self.r.calls),1)
    def test_inactive_during_unconfirmed_request(self):
        self.empty();self.tick(state='Inactive');self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
    def test_join_initial_wait(self):
        self.r.w.CurrentState='Inactive';self.restart();self.r.b.f.players=2;self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_unknown_state_fails_closed(self):
        self.tick(state='Unexpected');self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_wrong_owner_after_initial_wait(self):
        self.r.w.CurrentState='Inactive';self.restart();self.r.w.Owner=Node();self.tick(state='Active');self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_malformed_readback_after_initial_wait(self):
        self.r.w.CurrentState='Inactive';self.restart();self.r.pool.ServerSyncedLoadedAmmo=2;self.tick(state='Active');self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_wait_preserves_rolling_budget(self):
        for _ in range(10):self.empty();self.complete()
        self.swap(0);self.tick();self.tick(4,'Active');self.tick();self.empty();self.assertEqual(len(self.r.calls),10);self.tick(dt=31);self.assertEqual(len(self.r.calls),11)
    def test_disable_wait(self):
        self.swap(0);self.tick();self.a.tick(False);self.tick(4,'Active');self.empty();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
