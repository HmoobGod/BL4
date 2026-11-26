"""Synthetic persistent integration tests, including original real reload adapter."""
import unittest
from types import SimpleNamespace as N
from test_r3_persistent import Persistent
from test_reload_r20 import ReloadTests

class Lane:
    def __init__(self,kind,m):self.kind=kind;self.m=m;self.record=None;self.fault=False;self.ticks=0;self.begins=0;self.on_tick=None;self.rate=1.
    def begin(self):self.record=object();self.begins+=1;return True
    def tick(self,permitted):
        assert permitted;self.ticks+=1
        if self.on_tick:self.on_tick()
    def stop(self,reason):self.record=None

class Automation(unittest.TestCase):
    def setUp(self):
        self.p=Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups);self.m=self.p.m;self.now=100.;self.m.time=N(monotonic=lambda:self.now);self.lanes={}
        def factory(kind,session):
            lane=Lane(kind,self.m);self.lanes[kind]=lane;return lane
        self.m.make_automation_lane=factory
    def tick(self):self.now+=.3;self.p.tick()
    def arm(self,**values):
        self.p.configure(**values);self.m.apply({'persistent_automation_vacuum':True,'persistent_automation_reload':True,'vacuum_pref_ammo':True});self.tick();self.tick();self.tick()
    def test_default_no_automation(self):self.p.configure(walk_speed=2);self.tick();self.assertEqual(self.lanes,{})
    def test_both_lanes_and_ground(self):
        self.arm(walk_speed=2);self.m.ground_tick(self.p.anim);self.tick();self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.);self.assertTrue(all(l.ticks for l in self.lanes.values()));self.assertEqual(set(self.lanes),{'vacuum','reload'})
    def test_master_off_stops_and_restores(self):
        self.arm(walk_speed=2);self.m.ground_tick(self.p.anim);self.m.set_auto_setting(self.m.auto_master,False);self.assertTrue(all(l.record is None for l in self.lanes.values()));self.tick();self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_independent_disable(self):
        self.arm();r=self.lanes['reload'];v=self.lanes['vacuum'];self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['vacuum'],False);n=r.ticks;self.tick();self.assertIsNone(v.record);self.assertGreater(r.ticks,n)
    def test_ended_lane_no_retry(self):
        self.arm();v=self.lanes['vacuum'];v.record=None;self.tick();self.tick();self.assertIs(self.lanes['vacuum'],v);self.assertNotIn('vacuum',self.m._automation_leases)
        self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['vacuum'],False);self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['vacuum'],True);self.tick();self.assertIsNot(self.lanes['vacuum'],v)
    def test_rarity_modifier_coexists_with_automation(self):
        self.arm(legendary_weight=2);self.assertEqual(set(self.lanes),{'vacuum','reload'});self.assertEqual(self.p.f.weight,2.);self.assertTrue(all(l.record is not None for l in self.lanes.values()))
    def test_live_rarity_selection_keeps_automation(self):
        self.arm();before={k:l.ticks for k,l in self.lanes.items()};self.m.apply({'persistent_legendary_weight':True,'legendary_weight':2});self.tick();self.assertEqual(self.p.f.weight,2.);self.assertTrue(all(l.record is not None and l.ticks>before[k] for k,l in self.lanes.items()))
    def test_all_rarity_and_automation_lanes(self):
        from test_batch import Attr
        self.p.e.r.PearlescentModifier=Attr(1.)
        self.arm(common_weight=0.,uncommon_weight=.5,rare_weight=2.,epic_weight=3.,legendary_weight=4.,pearlescent_weight=5.)
        self.m.apply({o.identifier:True for o in self.m.AUTOMATION_OPTIONS.values()})
        for _ in range(10):self.tick()
        self.assertEqual(set(self.m._controller.records),self.m.RARITY_KEYS)
        self.assertEqual(set(self.m._automation_leases),set(self.m.AUTOMATION_OPTIONS))
        self.assertTrue(all(l.ticks>0 for l in self.lanes.values()))
        self.m.set_auto_setting(self.m.auto_master,False);self.tick()
        self.assertFalse(self.m._automation_leases);self.assertFalse(self.m._controller.records)
        self.assertEqual(self.p.f.weight,1.)
        for name in ('CommonModifier','UncommonModifier','RareModifier','VeryRareModifier','PearlescentModifier'):
            self.assertEqual(getattr(self.p.e.r,name).Value,1.)
    def test_rarity_foreign_drift_stops_automation_without_overwrite(self):
        self.arm(legendary_weight=2);before={k:l.ticks for k,l in self.lanes.items()};self.p.f.weight=7.;self.tick()
        self.assertEqual(self.p.f.weight,7.);self.assertTrue(self.m._controller.fault)
        self.assertTrue(all(l.record is None and l.ticks==before[k] for k,l in self.lanes.items()))
    def test_rarity_join_restores_and_stops_automation(self):
        self.arm(legendary_weight=2);before={k:l.ticks for k,l in self.lanes.items()};self.p.f.players=2;self.tick()
        self.assertEqual(self.p.f.weight,1.);self.assertTrue(all(l.record is None and l.ticks==before[k] for k,l in self.lanes.items()))
    def test_invalid_rarity_activation_stops_automation(self):
        self.arm();self.p.f.weight=.5;before={k:l.ticks for k,l in self.lanes.items()};self.m.apply({'persistent_legendary_weight':True,'legendary_weight':2});self.tick()
        self.assertEqual(self.p.f.weight,.5);self.assertIn('Activation failed',self.m._auto_blocked);self.assertTrue(all(l.record is None and l.ticks==before[k] for k,l in self.lanes.items()))
    def test_consent_loss_stops(self):self.arm();self.m.set_auto_setting(self.m.auto_consent,False);self.assertTrue(all(l.record is None for l in self.lanes.values()))
    def test_fault_stops_peer_and_restores(self):
        self.arm(walk_speed=2);self.m.ground_tick(self.p.anim);self.lanes['vacuum'].on_tick=lambda:setattr(self.lanes['vacuum'],'fault',True);r=self.lanes['reload'];n=r.ticks;self.tick();self.assertEqual(r.ticks,n);self.assertIsNone(r.record);self.assertTrue(self.m.health_fault());self.tick();self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_reentrant_monitor(self):
        self.arm();v=self.lanes['vacuum'];r=self.lanes['reload'];v.on_tick=self.m.monitor_tick;before=(v.ticks,r.ticks);self.tick();self.assertEqual((v.ticks,r.ticks),(before[0]+1,before[1]+1))
    def test_restore_all_blocks_restart(self):self.arm();self.m.request_stop('owner');self.tick();self.assertTrue(all(l.record is None for l in self.lanes.values()));self.assertFalse(self.m._automation_leases)
    def test_pending_multiplayer_no_start(self):self.p.f.players=2;self.arm();self.assertFalse(self.lanes)
    def test_save_failure_stops(self):self.arm();self.m.mod.fail_save=True;self.m.set_auto_setting(self.m.auto_master,False);self.assertTrue(all(l.record is None for l in self.lanes.values()))

class SessionReload(unittest.TestCase):
    def setUp(self):self.r=ReloadTests();self.r.setUp();self.addCleanup(self.r.doCleanups)
    def test_session_reload_after_30(self):
        r=self.r;m=r.m;m.apply({"persistent_master":True,"persistent_offline":True,"persistent_automation_reload":True});session=m.bound_session(r.b.f.sdk);a=m.make_automation_lane('reload',session);self.assertTrue(a.begin());r.now+=31;a.tick(True);self.assertIsNotNone(a.record)
        r.loaded=r.pool.LoadedAmmo=r.pool.ServerSyncedLoadedAmmo=0;r.w.CurrentState='Firing';r.now+=.2;a.tick(True);r.w.CurrentState='Active';r.now+=.2;a.tick(True);self.assertEqual(r.calls,[(0,0)])
    def test_original_weapon_scope_still_required(self):
        r=self.r;r.m.apply({"persistent_master":True,"persistent_offline":True,"persistent_automation_reload":True});a=r.m.make_automation_lane('reload',r.m.bound_session(r.b.f.sdk));self.assertTrue(a.begin());r.w.CurrentUseModeIndex=1;r.now+=1;a.tick(True);self.assertIsNone(a.record);self.assertFalse(r.calls)
    def test_actual_reload_monitor_with_vacuum_and_jump(self):
        r=self.r;m=r.m;real_factory=m.make_automation_lane;v=Lane('vacuum',m)
        m.make_automation_lane=lambda kind,session:v if kind=='vacuum' else real_factory(kind,session)
        m.apply({'persistent_master':True,'persistent_offline':True,'persistent_jump':True,'jump':1.5,'persistent_automation_vacuum':True,'persistent_automation_reload':True,'vacuum_pref_ammo':True})
        r.advance(dt=.3);r.advance(dt=.3);r.advance(dt=.3)
        self.assertIn('jump',m._controller.records);self.assertIn('reload',m._automation_leases);self.assertIsNotNone(v.record)
        r.empty();self.assertEqual(r.calls,[(0,0)]);self.assertGreater(v.ticks,0);self.assertIn('jump',m._controller.records)
    def test_both_actual_adapters_same_session(self):
        from test_vacuum_r25 import VacuumTests,Obj
        r=self.r;m=r.m;v=VacuumTests();from bl4_custom_foundation import loot_vacuum
        v.v=loot_vacuum;v.calls=[];v.lev=Obj('level',Class=Obj('/Script/Engine.Level'))
        r.p.Outer=v.lev;r.p._path_name=lambda:'LocalPawn';r.p.bHidden=False;r.p.IsActorBeingDestroyed=lambda:False
        r.p.CharacterMovement.IsMovingOnGround=lambda:True
        r.p.K2_GetActorLocation=v.func(loot_vacuum.LOCATION,loot_vacuum.LOC_SIG,lambda:N(X=0,Y=0,Z=0))
        drop=v.drop('ammo','ammo',(300,0,0));sdk=r.b.f.sdk;old=sdk.find_all
        sdk.find_all=lambda name,**kw:[drop] if name=='InventoryPickup' else [] if name=='OakVendingMachine' else old(name,**kw)
        sdk.make_struct=lambda name,**kw:N(**kw)
        m.apply({'persistent_master':True,'persistent_offline':True,'persistent_jump':True,'jump':1.5,'persistent_automation_vacuum':True,'persistent_automation_reload':True,'vacuum_pref_ammo':True,'persistent_legendary_weight':True,'legendary_weight':2.})
        for _ in range(4):r.advance(dt=.3)
        self.assertIn('jump',m._controller.records);self.assertIn('legendary_weight',m._controller.records);self.assertEqual(r.b.f.weight,2.);self.assertEqual(set(m._automation_leases),{'vacuum','reload'});self.assertEqual(len(v.calls),1)
        r.empty();self.assertEqual(r.calls,[(0,0)]);r.advance(dt=1);self.assertEqual(len(v.calls),1)
        m.set_auto_setting(m.auto_master,False);r.advance(dt=1);self.assertFalse(m._automation_leases);self.assertFalse(m._controller.records);self.assertEqual(r.b.f.weight,1.)
