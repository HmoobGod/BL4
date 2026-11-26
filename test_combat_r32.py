"""R32 synthetic persistent reload and existing ammo regeneration, not native gameplay."""
from test_combat_r31 import PersistentFire
from test_movement_r29 import ReloadRecovery
from test_combat_r13 import attr,desc,Node

class PersistentReload(PersistentFire):
    def setUp(self):
        super().setUp()
        self.reload=self.w.behaviors[1].ReloadTime;self.minimum=self.w.behaviors[1].MinReloadTime
        self.rate,self.delay=self.regen(self.r.pool)
    def regen(self,pool):
        rate,delay=attr(2.),attr(4.);pool.RegenRate=rate;pool.ConsumeRegenDelay=delay
        prior=list(pool.Class._properties());pool.Class._properties=lambda:prior+[desc('RegenRate',rate._type),desc('ConsumeRegenDelay',delay._type)]
        return rate,delay
    def test_defaults_off(self):
        self.m.apply({'reload':2.,'ammo_regen_rate':2.,'ammo_regen_delay':2.});self.arm();self.assertFalse(self.reload.writes+self.rate.writes+self.delay.writes)
    def test_all_with_native_reload(self):
        self.arm(reload=2.,ammo_regen_rate=2.,ammo_regen_delay=2.,fire_rate=2.)
        self.assertEqual((self.reload.Value,self.rate.Value,self.delay.Value),(1.5,4.,2.));self.r.empty();self.assertEqual(self.r.calls,[(0,0)]);self.assertIsNotNone(self.v.record)
        self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual((self.reload.Value,self.rate.Value,self.delay.Value),(3.,2.,4.))
    def test_reload_floor_wait_other_control(self):
        self.minimum._values.update(Value=2.,BaseValue=2.);self.arm(reload=3.,jump=1.5);self.assertFalse(self.reload.writes);self.assertIn('jump',self.m._controller.records);self.assertFalse(self.m._auto_blocked)
    def test_floor_drift_restores(self):
        self.arm(reload=2.);self.minimum._values.update(Value=2.,BaseValue=2.);self.tick();self.assertEqual(self.reload.Value,3.);self.assertFalse(self.m._controller.records);self.assertTrue(self.m._auto_blocked)
    def test_busy_update_waits(self):
        self.arm(reload=2.);self.w.CurrentState='Reloading';self.m.apply({'reload':3.});self.tick(2);self.assertEqual(self.reload.Value,1.5);self.w.CurrentState='Active';self.tick();self.assertEqual(self.reload.Value,1.)
    def test_no_new_regen(self):
        self.rate._values.update(Value=0.,BaseValue=0.);self.arm(ammo_regen_rate=2.,ammo_regen_delay=2.,reload=2.);self.assertFalse(self.rate.writes+self.delay.writes);self.assertEqual(self.reload.Value,1.5);self.assertFalse(self.m._auto_blocked)
    def test_pending_restores_all_weapon_rates(self):
        self.arm(reload=2.,ammo_regen_rate=2.,ammo_regen_delay=2.,jump=1.5);self.r.p.ActiveWeapons.Slots[0].PendingWeapon=self.w;self.tick();self.assertEqual((self.reload.Value,self.rate.Value,self.delay.Value),(3.,2.,4.));self.assertEqual(set(self.m._controller.records),{'jump'});self.r.p.ActiveWeapons.Slots[0].PendingWeapon=None;self.tick(4);self.assertEqual((self.reload.Value,self.rate.Value,self.delay.Value),(1.5,4.,2.))
    def test_join_restores(self):
        self.arm(reload=2.,ammo_regen_rate=2.,ammo_regen_delay=2.);self.r.b.f.players=2;self.tick();self.assertEqual((self.reload.Value,self.rate.Value,self.delay.Value),(3.,2.,4.));self.assertFalse(self.m._automation_leases)
    def test_original_lost_no_replacement(self):
        self.arm(reload=2.,ammo_regen_rate=2.);new=self.r.c.weapon(attr(5.),attr(4.),attr(.5));self.r.p.ActiveWeapons.Slots=[self.r.c.slot(new)];self.tick();self.assertTrue(self.m._controller.fault);self.assertFalse(new.behaviors[1].ReloadTime.writes)
    def test_regen_loss_stops_delay(self):
        self.arm(ammo_regen_delay=2.);self.rate._values.update(Value=0.,BaseValue=0.);self.tick();self.assertEqual(self.delay.Value,4.);self.assertTrue(self.m._auto_blocked)

class LastReserve(ReloadRecovery):
    def test_last_reserve_auto_completion_then_resume(self):
        self.empty();self.reserves(0);self.tick(state='Reloading');self.tick(3,'Active');self.tick(3,'Active');self.assertTrue(self.a.reserve_paused);self.assertIsNotNone(self.a.record);self.assertEqual(len(self.r.calls),1);self.reserves(20);self.tick();self.empty();self.assertEqual(len(self.r.calls),2)
    def test_external_last_reserve(self):
        self.reserves(0);self.tick(2,'Reloading');self.tick(3,'Active');self.tick(3,'Active');self.assertTrue(self.a.reserve_paused);self.assertFalse(self.r.calls);self.reserves(20);self.tick();self.empty();self.assertEqual(len(self.r.calls),1)
    def test_empty_completion_timeout(self):
        self.empty();self.reserves(0);self.tick(state='Reloading');self.tick(0,'Active');self.tick(0,'Active',dt=11);self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
    def test_zero_reserve_swap_inflight_stops(self):
        self.empty();self.reserves(0);self.tick(state='Reloading');self.swap();self.tick();self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
