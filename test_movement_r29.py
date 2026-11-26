"""R29 persistent local movement and reload lifecycle, synthetic only."""
from test_automation_r27 import Automation
from test_automation_r28 import SwapReload
from test_combat_r13 import Node,attr,typ,desc
from test_r7 import ELEMENTS

class PersistentMovement(Automation):
    def setUp(self):
        super().setUp();p=self.p.f.pawn
        self.dash=attr(1200.);self.glide=attr(800.)
        self.comp=p.CharacterMovement
        self.comp.Class=typ('OakCharacterMovementComponent',desc('DashSpeed',self.dash._type),desc('GlidingSpeed',self.glide._type))
        self.comp._path_name=lambda:'OwnedMovement';self.comp.OakCharacterOwner=p
        self.comp.DashSpeed=self.dash;self.comp.GlidingSpeed=self.glide
    def vals(self):return (self.dash.Value,self.dash.BaseValue,self.glide.Value,self.glide.BaseValue)
    def test_default_off(self):
        self.m.apply({'dash_speed':2.,'glide_speed':2.,'persistent_master':True,'persistent_offline':True});self.tick();self.assertEqual(self.vals(),(1200.,1200.,800.,800.))
    def test_coexist_and_restore(self):
        self.arm(dash_speed=2.,glide_speed=1.5,shock_damage=2.,fire_damage=2.);self.tick();self.assertEqual(self.vals(),(2400.,2400.,1200.,1200.));self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'});self.assertEqual(self.p.f.pawn.ElementalDamageModifiers.ShockModifier.Value,2.);self.assertEqual(self.p.b.fire.Value,2.)
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['dash_speed'],False);self.tick();self.assertEqual(self.vals(),(1200.,1200.,1200.,1200.));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.vals(),(1200.,1200.,800.,800.));self.assertEqual(self.p.b.fire.Value,1.);self.assertFalse(self.m._automation_leases)
    def test_saved_flags_relaunch(self):
        self.p.configure(dash_speed=2.,glide_speed=.5);saved=self.m.mod.saved;self.m.apply({'persistent_master':False,'persistent_dash_speed':False,'persistent_glide_speed':False});self.m.mod.restore(saved);self.m.enabled();self.tick();self.tick();self.assertEqual(self.vals(),(2400.,2400.,400.,400.))
    def test_update_and_neutral(self):
        self.arm(dash_speed=2.,glide_speed=.5);self.m.apply({'dash_speed':3.,'glide_speed':1.});self.tick();self.assertEqual(self.vals(),(3600.,3600.,800.,800.));self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
    def test_join(self):
        self.arm(dash_speed=2.,glide_speed=2.);self.p.f.players=2;self.tick();self.assertEqual(self.vals(),(1200.,1200.,800.,800.));self.assertFalse(self.m._controller.records)
    def test_foreign_owner(self):
        self.comp.OakCharacterOwner=Node();self.p.configure(dash_speed=2.);self.tick();self.assertFalse(self.dash.writes)
    def test_drift_fault_stops_automation(self):
        self.arm(dash_speed=2.,glide_speed=2.);self.dash._values['Value']=999.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.dash.Value,999.);self.assertFalse(self.m._automation_leases)
    def test_all_elements_compatible(self):
        self.arm(**dict.fromkeys(ELEMENTS,2.));self.tick();self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'});self.assertEqual(set(self.m._controller.records),set(ELEMENTS));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertFalse(self.m._controller.records)

class ReloadRecovery(SwapReload):
    def reserves(self,n):self.r.pool.StoredAmmo=self.r.pool.SpareAmmo=n
    def test_resume_after_reserve_recovery(self):
        self.reserves(0);self.empty();self.assertIsNotNone(self.a.record);self.reserves(20);self.tick();self.assertFalse(self.r.calls);self.tick(4,'Active');self.empty();self.assertEqual(len(self.r.calls),1)
    def test_reserve_loss_inflight_stops(self):
        self.empty();self.reserves(0);self.tick(state='Reloading');self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
    def test_pause_scope_loss(self):
        self.reserves(0);self.tick();self.r.b.f.players=2;self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def switch_mode(self):
        r=self.r;w=r.w;new=r.c.weapon(attr(8.),attr(3.),attr(.5));pool=Node(**vars(r.pool));pool.Outer=w;pool.Name='UM1_AmmoPool';pool.LoadedAmmo=pool.ServerSyncedLoadedAmmo=4
        for b in new.behaviors:b.Outer=w;b.Name=b.Name.replace('UM0_','UM1_')
        w.behaviors.extend([*new.behaviors,pool]);w.CurrentUseModeIndex=1;r.pool=pool;r.loaded=4
    def test_distinct_supported_mode(self):
        self.tick(0,'Firing');self.switch_mode();self.tick(state='Active');self.assertFalse(self.r.calls);self.tick();self.empty();self.assertEqual(self.r.calls,[(1,0)])
    def test_mode_during_request_stops(self):
        self.empty();self.switch_mode();self.tick();self.assertIsNone(self.a.record);self.assertEqual(self.r.calls,[(0,0)])
    def test_pause_budget_preserved(self):
        for _ in range(10):self.empty();self.complete()
        self.reserves(0);self.tick();self.reserves(20);self.tick();self.empty();self.assertEqual(len(self.r.calls),10);self.tick(dt=31);self.assertEqual(len(self.r.calls),11)
