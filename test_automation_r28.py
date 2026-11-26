"""R28 lifecycle extensions, synthetic only."""
import unittest
from test_reload_r20 import ReloadTests
from test_combat_r13 import attr,Node
from test_vacuum_r26 import Continuous
from test_automation_r27 import Automation

class SwapReload(unittest.TestCase):
    def setUp(self):
        self.r=ReloadTests();self.r.setUp();self.addCleanup(self.r.doCleanups);r=self.r;m=r.m
        m.apply({'persistent_master':True,'persistent_offline':True,'persistent_automation_reload':True})
        self.a=m.make_automation_lane('reload',m.bound_session(r.b.f.sdk));self.assertTrue(self.a.begin())
    def tick(self,loaded=None,state=None,dt=.2):
        r=self.r
        if loaded is not None:r.loaded=r.pool.LoadedAmmo=r.pool.ServerSyncedLoadedAmmo=loaded
        if state is not None:r.w.CurrentState=state
        r.now+=dt;self.a.tick(True)
    def empty(self):self.tick(0,'Firing');self.tick(state='Active')
    def complete(self):self.tick(state='Reloading');self.tick(8,'Active');self.tick(8,'Active')
    def swap(self,loaded=4,foreign=False):
        r=self.r;old=r.w;old.CurrentState='Inactive';w=r.c.weapon(attr(8.),attr(3.),attr(.5))
        # Independent native-shaped behavior object and pool identity for new weapon.
        pool=Node(**vars(r.pool));pool.Outer=w;pool.LoadedAmmo=pool.ServerSyncedLoadedAmmo=loaded
        w.behaviors.append(pool);w.ServerStartReloading=old.ServerStartReloading
        if foreign:w.Owner=Node()
        r.p.ActiveWeapons.Slots.append(r.c.slot(w));r.w=w;r.pool=pool;r.loaded=loaded
    def test_swap_fresh_cycle(self):
        self.tick(0,'Firing');self.swap();self.tick();self.assertFalse(self.r.calls);self.tick();self.empty();self.assertEqual(len(self.r.calls),1)
    def test_pending_pauses_and_resumes(self):
        r=self.r;self.tick(0,'Firing');r.p.ActiveWeapons.Slots[0].PendingWeapon=r.w;self.tick(state='Active');self.assertFalse(r.calls);self.assertIsNotNone(self.a.record)
        r.p.ActiveWeapons.Slots[0].PendingWeapon=None;self.swap();self.tick();self.tick();self.empty();self.assertEqual(len(r.calls),1)
    def test_swap_empty_no_dispatch(self):self.swap(0);self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_swap_foreign_stops(self):self.swap(foreign=True);self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_swap_during_unconfirmed_reload_stops(self):self.empty();self.swap();self.tick();self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
    def test_rolling_limit(self):
        for _ in range(10):self.empty();self.complete()
        self.assertEqual(len(self.r.calls),10);self.empty();self.assertEqual(len(self.r.calls),10);self.assertIsNotNone(self.a.record)
        self.tick(dt=31);self.assertEqual(len(self.r.calls),11)
    def test_rolling_limit_survives_swap(self):
        for _ in range(10):self.empty();self.complete()
        self.swap();self.tick();self.tick();self.empty();self.assertEqual(len(self.r.calls),10);self.tick(dt=31);self.assertEqual(len(self.r.calls),11)
    def test_pending_permission_loss(self):
        self.r.p.ActiveWeapons.Slots[0].PendingWeapon=self.r.w;self.tick();self.r.b.f.players=2;self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_new_weapon_session_change(self):self.swap();self.r.b.f.players=2;self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)

class LiveVacuum(Continuous):
    def test_live_filter_radius_ledger(self):
        self.actors.append(self.drop('cash','cash',(800,0,0)));self.start(radius=5);self.tick();self.assertEqual(len(self.calls),1)
        lease=self.lease;record=lease.record;self.assertTrue(lease.update_preferences(('cash',),10));self.tick();self.assertEqual([c[0] for c in self.calls],['a','cash'])
        lease.update_preferences(('ammo','cash'),30);self.tick(31);self.assertEqual(len(self.calls),2);self.assertIs(lease.record,record);self.assertEqual(lease.total_attempts,2)
    def test_empty_filters_pause(self):
        self.start();self.lease.update_preferences((),30);self.tick();self.assertFalse(self.calls);self.assertIsNotNone(self.lease.record)
        self.lease.update_preferences(('ammo',),30);self.tick();self.assertEqual(len(self.calls),1)
    def test_empty_filters_still_guard_session(self):self.start();self.lease.update_preferences((),30);self.ok=False;self.tick();self.assertIsNone(self.lease.record)
    def test_invalid_update_preserves_previous(self):
        self.start();self.assertRaises(ValueError,self.lease.update_preferences,('unknown',),30);self.assertEqual(self.lease.categories,{'ammo'});self.tick();self.assertEqual(len(self.calls),1)
    def test_update_reentrant_refused(self):
        self.start();old=self.a.K2_GetActorRotation
        def edit():self.assertFalse(self.lease.update_preferences((),30));return old()
        edit.func=old.func;self.a.K2_GetActorRotation=edit;self.tick();self.assertEqual(len(self.calls),1)

class Coexist(Automation):
    def test_recovery_fields_compatible(self):
        self.arm(damage_taken=.5,repair_cooldown=.5,healing_received=2,repair_duration=2);self.tick();self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'});self.assertEqual(set(self.m._controller.records),{'damage_taken','repair_cooldown','healing_received','repair_duration'});self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertFalse(self.m._controller.records)
    def test_live_saved_preferences_dispatch(self):
        self.arm();v=self.lanes['vacuum'];changes=[];v.update_preferences=lambda categories,radius:changes.append((categories,radius));self.m._vacuum_filters['cash']=True;self.m._vacuum_radius=45;self.m.save_vacuum_preferences();self.tick();self.assertIs(self.lanes['vacuum'],v);self.assertEqual(changes[-1],(('cash',),45.))
