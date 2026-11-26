"""Persistent weapon-only transitions and external reload observation, synthetic."""
import unittest
from test_reload_r20 import ReloadTests
from test_combat_r13 import attr,desc,Node
from test_automation_r27 import Lane
from test_automation_r28 import SwapReload

class PersistentFire(unittest.TestCase):
    def setUp(self):
        self.r=ReloadTests();self.r.setUp();self.addCleanup(self.r.doCleanups)
        self.m=self.r.m;self.w=self.r.w;self.fire=self.w.behaviors[0]
        self.spread,self.recoil=self.tune(self.fire)
        self.v=Lane('vacuum',self.m);factory=self.m.make_automation_lane
        self.m.make_automation_lane=lambda k,s:self.v if k=='vacuum' else factory(k,s)
    def tune(self,f):
        s,r=attr(4.),attr(2.);f.spread=s;f.RecoilScale=r
        props=list(f.Class._properties());f.Class._properties=lambda:props+[desc('spread',s._type),desc('RecoilScale',r._type)]
        return s,r
    def tick(self,n=1):
        for _ in range(n):self.r.advance(dt=.3)
    def arm(self,**values):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_automation_reload':True,'persistent_automation_vacuum':True,'vacuum_pref_ammo':True,**values,**{'persistent_'+k:True for k in values}});self.tick(6)
    def test_default_off(self):
        self.m.apply({'fire_rate':2.,'weapon_spread':.5,'weapon_recoil':.5});self.arm();self.assertEqual(self.fire.firerate.writes+self.spread.writes+self.recoil.writes,[])
    def test_coexist_actual_reload(self):
        self.arm(fire_rate=2.,weapon_spread=.5,weapon_recoil=.5,jump=1.5);self.assertEqual((self.fire.firerate.Value,self.spread.Value,self.recoil.Value),(16.,2.,1.));self.r.empty();self.assertEqual(self.r.calls,[(0,0)]);self.assertIsNotNone(self.v.record);self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual((self.fire.firerate.Value,self.spread.Value,self.recoil.Value),(8.,4.,2.))
    def test_busy_update_waits(self):
        self.arm(fire_rate=2.);self.w.CurrentState='Firing';self.m.apply({'fire_rate':3.});self.tick(2);self.assertEqual(self.fire.firerate.Value,16.);self.assertFalse(self.m._auto_blocked);self.w.CurrentState='Active';self.tick();self.assertEqual(self.fire.firerate.Value,24.)
    def test_pending_restores_only_weapon(self):
        self.arm(fire_rate=2.,weapon_recoil=.5,jump=1.5);self.r.p.ActiveWeapons.Slots[0].PendingWeapon=self.w;self.tick();self.assertEqual((self.fire.firerate.Value,self.recoil.Value),(8.,2.));self.assertEqual(set(self.m._controller.records),{'jump'});self.assertFalse(self.m._auto_blocked);self.assertIsNotNone(self.v.record);self.r.p.ActiveWeapons.Slots[0].PendingWeapon=None;self.tick(4);self.assertEqual((self.fire.firerate.Value,self.recoil.Value),(16.,1.))
    def test_swap_restores_then_rebinds(self):
        self.arm(fire_rate=2.,weapon_spread=.5,jump=1.5);self.w.CurrentState='Inactive';new=self.r.c.weapon(attr(5.),attr(3.),attr(.5));s,_=self.tune(new.behaviors[0]);self.r.p.ActiveWeapons.Slots.append(self.r.c.slot(new));self.tick(4);self.assertEqual((self.fire.firerate.Value,self.spread.Value),(8.,4.));self.assertEqual((new.behaviors[0].firerate.Value,s.Value),(10.,2.));self.assertIn('jump',self.m._controller.records)
    def test_mode_change_restores_distinct_behavior(self):
        self.arm(fire_rate=2.,weapon_recoil=.5);new=self.r.c.weapon(attr(5.),attr(3.),attr(.5));_,r=self.tune(new.behaviors[0])
        for b in new.behaviors:b.Outer=self.w;b.Name=b.Name.replace('UM0_','UM1_')
        self.w.behaviors.extend(new.behaviors);self.w.CurrentUseModeIndex=1;self.tick(4)
        self.assertEqual((self.fire.firerate.Value,self.recoil.Value),(8.,2.));self.assertEqual((new.behaviors[0].firerate.Value,r.Value),(10.,1.));self.assertFalse(self.m._auto_blocked)
    def test_original_removed_fault(self):
        self.arm(fire_rate=2.,jump=1.5);self.r.p.ActiveWeapons.Slots=[];self.tick();self.assertTrue(self.m._controller.fault);self.assertFalse(self.m._automation_leases);self.assertEqual(self.fire.firerate.Value,16.);self.assertNotIn('jump',self.m._controller.records)
    def test_unsupported_weapon_other_features_continue(self):
        self.w.Class.Name='HeavyWeaponGadget';self.arm(fire_rate=2.,jump=1.5);self.assertFalse(self.fire.firerate.writes);self.assertIn('jump',self.m._controller.records);self.assertFalse(self.m._auto_blocked)
    def test_join_restore(self):
        self.arm(fire_rate=2.,weapon_recoil=.5);self.r.b.f.players=2;self.tick();self.assertEqual((self.fire.firerate.Value,self.recoil.Value),(8.,2.));self.assertFalse(self.m._controller.records);self.assertFalse(self.m._automation_leases)
    def test_foreign_drift(self):
        self.arm(weapon_spread=.5);self.spread._values['Value']=3.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.spread.Value,3.);self.assertFalse(self.m._automation_leases)

class ExternalReload(SwapReload):
    def test_manual_reload_then_auto(self):
        self.tick(2,'Reloading');self.assertFalse(self.r.calls);self.tick(8,'Active');self.tick(8,'Active');self.empty();self.assertEqual(self.r.calls,[(0,0)])
    def test_interrupted_manual_no_dispatch(self):
        self.tick(0,'Reloading');self.tick(0,'Firing');self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_manual_timeout(self):
        self.tick(2,'Reloading');self.tick(2,'Reloading',dt=11);self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_manual_reload_swap_stops(self):
        self.tick(2,'Reloading');self.swap();self.tick();self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
