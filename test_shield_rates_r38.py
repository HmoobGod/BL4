"""Persistent shield transitions, native-shaped mocks, no game execution."""
from types import SimpleNamespace as N
from test_shield_rates_r37 import ShieldRates
from test_automation_r27 import Lane
from test_combat_r13 import Node

class PersistentShield(ShieldRates):
    def setUp(self):
        super().setUp();self.now=100.;self.m.time=N(monotonic=lambda:self.now);self.lanes={}
        self.b.f.solo=True
        self.m.close_menu();self.b.gui.finish_close()
        def factory(kind,session):
            lane=Lane(kind,self.m);self.lanes[kind]=lane;return lane
        self.m.make_automation_lane=factory
    def tick(self,n=1):
        for _ in range(n):
            self.now+=.3;self.m._auto_next=0.;self.m.monitor_tick()
    def arm(self,**settings):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**settings});self.tick(5)
    def test_persistent_defaults_off(self):
        self.arm(shield_regen_rate=2.,shield_regen_delay=2.);self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.sh.RegenRate.writes+self.sh.RegenDelay.writes)
    def test_persistent_independent_live_restore(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_shield_regen_delay=True,shield_regen_delay=2.)
        self.assertEqual(self.values(),(20.,20.,2.,2.));self.m.apply({'shield_regen_rate':3.,'shield_regen_delay':1.});self.tick(2);self.assertEqual(self.values(),(30.,30.,4.,4.));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.values(),(10.,10.,4.,4.))
    def test_persistent_swap_both(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_shield_regen_delay=True,shield_regen_delay=2.,persistent_jump=True,jump=2.)
        self.current=self.make_shield();self.current.RegenRate._values.update(Value=15.,BaseValue=15.);self.current.RegenDelay._values.update(Value=6.,BaseValue=6.);self.tick(3)
        self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertEqual(self.values(self.current),(30.,30.,3.,3.));self.assertEqual(self.b.jump.JumpZVelocity,1240.);self.assertFalse(self.m._controller.fault)
        self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.values(self.current),(15.,15.,6.,6.))
    def test_persistent_swap_armor_wait(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_jump=True,jump=2.);self.current=self.make_shield();self.current.system='Armor';self.tick(3)
        self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.current.RegenRate.writes);self.assertIn('jump',self.m._controller.records)
        self.current=self.make_shield();self.tick();self.assertEqual(self.values(self.current),(20.,20.,4.,4.))
    def test_persistent_swap_missing_wait(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.);self.current=None;self.tick(3);self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.m._controller.fault)
        self.current=self.make_shield();self.tick();self.assertEqual(self.values(self.current),(20.,20.,4.,4.))
    def test_persistent_original_owner_loss_fault(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_jump=True,jump=2.);self.current=self.make_shield();self.sh.OwningCharacter=Node();self.tick();self.assertTrue(self.m._controller.fault);self.assertFalse(self.current.RegenRate.writes);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_persistent_no_rebind_on_foreign_drift(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.);self.sh.RegenRate._values['Value']=19.;self.current=self.make_shield();self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.sh.RegenRate.Value,19.);self.assertFalse(self.current.RegenRate.writes)
    def test_persistent_unsupported_initial_no_global_block(self):
        self.sh.system='Bio';self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_jump=True,jump=2.);self.assertFalse(self.sh.RegenRate.writes);self.assertIn('jump',self.m._controller.records);self.assertFalse(self.m._auto_blocked)
    def test_persistent_join_restores(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_shield_regen_delay=True,shield_regen_delay=.5);self.b.f.players=2;self.tick();self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.m._controller.records)
    def test_persistent_getter_drift_fault(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.);self.member(self.sh,'GetRegenRate','ZFloatProperty',lambda:99.);self.tick();self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertTrue(self.m._controller.fault)
    def test_native_shield_priority_other_lanes_independent(self):
        self.arm(persistent_automation_shield=True,persistent_automation_health=True,persistent_automation_reload=True,persistent_automation_vacuum=True,vacuum_pref_ammo=True);self.assertEqual(set(self.m._automation_leases),{'shield','health','reload','vacuum'})
        old=self.lanes['shield'];n=old.ticks;self.m.apply({'persistent_shield_regen_rate':True,'shield_regen_rate':2.});self.tick();self.assertEqual(self.values(),(20.,20.,4.,4.));self.assertIsNone(old.record);self.assertEqual(old.ticks,n);self.assertEqual(set(self.m._automation_leases),{'health','reload','vacuum'})
        self.m.apply({'shield_regen_rate':1.});self.tick(3);self.assertNotIn('shield',self.m._automation_leases);self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['shield'],False);self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['shield'],True);self.tick(2);self.assertIn('shield',self.m._automation_leases)
    def test_conflict_while_unsupported_prevents_shield_pulse(self):
        self.sh.system='Armor';self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.,persistent_automation_shield=True,persistent_automation_health=True);self.assertNotIn('shield',self.m._automation_leases);self.assertIn('health',self.m._automation_leases);self.assertFalse(self.sh.RegenRate.writes)
    def test_saved_flags(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_shield_regen_delay':True,'shield_regen_delay':2.});saved=self.m.mod.saved;self.m.apply({'persistent_master':False,'persistent_shield_regen_delay':False});self.m.mod.restore(saved);self.m.enabled();self.tick();self.assertEqual(self.values(),(10.,10.,2.,2.))
    def test_draft_does_not_change_active_value(self):
        self.arm(persistent_shield_regen_rate=True,shield_regen_rate=2.);self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY['shield_regen_rate'],3.);self.tick();self.assertEqual(self.values(),(20.,20.,4.,4.));self.m.flush_auto_edits(force=True);self.tick();self.assertEqual(self.values(),(30.,30.,4.,4.))

from test_recovery_r34 import ContinuousRecovery
from test_combat_r13 import objdesc
from test_shield_rates_r37 import PATH, SHIELD

class RealRecoveryShield(ContinuousRecovery):
    make_shield=ShieldRates.make_shield
    member=ShieldRates.member
    def setUp(self):
        super().setUp();self.p=self.h.p;self.gear=self.make_shield()
        ps=[objdesc('ShieldUser','/Script/Engine.Actor'),objdesc('ReturnValue',SHIELD)]
        cdo=Node();f=Node(Name='GetShield',NumParams=2,Outer=Node(ClassDefaultObject=cdo),_path_name=lambda:PATH,_properties=lambda:ps)
        def get(p):self.assertIs(p,self.p);return self.gear
        get.func=f;cdo.GetShield=get;old=self.h.b.f.sdk.find_all
        self.h.b.f.sdk.find_all=lambda *a,**k:list(old(*a,**k))+[f] if a[0]=='Function' else old(*a,**k)
    def test_actual_pulse_stops_only_shield(self):
        self.arm('health','shield');self.shield._values['Value']=55.;self.tick();self.shield._values['Value']=60.;self.tick();self.assertIn(('shield',.01),self.calls)
        before=len([c for c in self.calls if c[0]=='shield']);self.m.apply({'persistent_shield_regen_rate':True,'shield_regen_rate':2.});self.shield._values['Value']=65.;self.tick();self.shield._values['Value']=70.;self.tick()
        self.assertEqual(self.gear.RegenRate.Value,20.);self.assertIn('health',self.m._automation_leases);self.assertNotIn('shield',self.m._automation_leases);self.assertEqual(len([c for c in self.calls if c[0]=='shield']),before)
        self.assertGreater(len([c for c in self.calls if c[0]=='health']),0)
