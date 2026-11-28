"""Synthetic native reload rate and independent minimum witness. No game execution."""
import unittest
from test_native_resource_rates import NativeRateTests, Modifier, Result, WrappedStruct
from test_combat_r13 import Combat, Node, attr
from test_double_jump_r52 import p,t

class NativeReloadRateTests(unittest.TestCase):
    def setUp(self):
        self.n=NativeRateTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        from bl4_custom_foundation.native_weapon_damage import make_reload_trial
        self.make_trial=make_reload_trial;self.R=self.n.R;self.w=self.c.w;self.pawn=self.c.p
        self.pc=Node(Class=t('OakPlayerController','/Script/OakGame.OakPlayerController'),Pawn=self.pawn)
        self.pawn.Class._path_name=lambda:'/Script/OakGame.OakCharacter';self.pawn._path_name=lambda:'Test.PlayerPawn'
        self.w.Class._path_name=lambda:'/Script/OakGame.OakWeapon'
        self.behavior=self.w.behaviors[1];self.a=self.c.reload;self.minimum=self.c.minimum
        base=t('WeaponBehavior_Reload',self.R.WEAPON_RELOAD);self.behavior.Class._superfields=lambda:iter((base,))
        self.ctx=Node(_type=t('WeaponAttributeContextResolver',self.R.WEAPON_CONTEXT,p('BehaviorTypeToFurtherResolveTo','ZSoftClassProperty',MetaClass=t('WeaponBehavior','/Script/GbxWeapon.WeaponBehavior')),p('usemodebitmask','ZUInt32Property')),BehaviorTypeToFurtherResolveTo=base,usemodebitmask=0)
        self.n.attr.definitions['weapon_reload_time'].Context=self.ctx
        # Build a separate read-only exact minimum definition in the fixture.
        self.R.TARGETS['_fixture_min']=('weapon_min_reload_time','MinReloadTime',self.R.WEAPON_CONTEXT,self.R.WEAPON_RELOAD,'ScaleMultiply',1.)
        try:self.n.create_def('_fixture_min')
        finally:del self.R.TARGETS['_fixture_min']
        self.n.attr.definitions['weapon_min_reload_time'].Context=self.ctx
        self.ok=True;self.allowed=True;self.calls=[];self.min_override=None;self.rate_override=None
        self.binding=self.n.binding
        self.binding.calls.update(GetValueOfAttribute=self.get,AddModifierToGbxAttribute=self.add,RemoveAttributeModifier=self.remove)
        self.lane=self.make(2.)
    def make(self,selection):
        return self.make_trial(self.binding,lambda:(self.pc,self.pawn,self.n.world,self.ok),lambda o:lambda:o,lambda:self.n.now,lambda:self.n.tid,self.n.msg.append,lambda:self.allowed,selection)
    def get(self,name,obj,default):
        self.assertIs(obj,self.w)
        if name=='weapon_min_reload_time':return self.minimum.Value if self.min_override is None else self.min_override
        self.assertEqual(name,'weapon_reload_time');return self.a.Value if self.rate_override is None else self.rate_override
    def add(self,d,obj,m,amount,refresh,result):
        self.assertEqual(d._name,'weapon_reload_time');self.assertIs(obj,self.w);self.assertEqual(m,Modifier.ScaleMultiply);self.assertIs(refresh,True)
        self.calls.append(('add',amount));self.a._values['Value']*=amount
        return WrappedStruct(_type=self.n.handle_type),d,Result.Success
    def remove(self,h):
        self.calls.append(('remove',));self.a._values['Value']=3.
        return True,WrappedStruct(_type=self.n.handle_type)
    def tick(self,dt=.3):self.n.now+=dt;self.lane.tick(True)
    def start(self):
        self.assertTrue(self.lane.begin(),self.n.msg);self.tick();self.assertEqual(self.lane.phase,'active',self.n.msg)
    def finish(self):
        self.tick();self.tick();self.assertEqual(self.lane.phase,'done',self.n.msg);self.assertEqual(self.a.Value,3.);self.assertEqual(self.a.BaseValue,3.);self.assertFalse(self.a.writes);self.assertFalse(self.minimum.writes)
    def test_inverse_and_normal_reload(self):
        self.start();self.assertEqual(self.a.Value,1.5);self.w.CurrentState='Reloading';self.tick();self.assertEqual(self.lane.phase,'active');self.lane.stop('test');self.finish();self.assertEqual(self.calls,[('add',.5),('remove',)])
    def test_slower_selection(self):
        self.lane=self.make(.5);self.start();self.assertEqual(self.a.Value,6.);self.lane.stop('test');self.finish()
    def test_initial_floor(self):
        self.minimum._values.update(Value=2.,BaseValue=2.);self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_independent_minimum(self):
        self.min_override=1.;self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_minimum_late_change(self):
        self.assertTrue(self.lane.begin());self.minimum._values.update(Value=1.,BaseValue=1.);self.tick();self.assertFalse(self.calls)
    def test_minimum_active_change_removes_only_handle(self):
        self.start();self.minimum._values.update(Value=2.,BaseValue=2.);self.tick();self.assertTrue(self.lane.fault);self.assertEqual(self.calls,[('add',.5),('remove',)]);self.assertEqual(self.minimum.Value,2.)
    def test_mode_switch(self):
        self.start();self.w.CurrentUseModeIndex=1;self.finish();self.assertEqual(self.calls,[('add',.5),('remove',)])
    def test_join_cleanup(self):
        self.start();self.ok=False;self.finish()
    def test_ambiguous_reload(self):
        self.w.behaviors.append(Node(Name='UM1_ExtraReload',Outer=self.w,Class=self.behavior.Class));self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_non_idle_before_dispatch(self):
        self.assertTrue(self.lane.begin());self.w.CurrentState='Reloading';self.tick();self.assertFalse(self.calls)
    def test_missing_original(self):
        self.start();self.pawn.ActiveWeapons.Slots=[];self.tick();self.assertTrue(self.lane.fault);self.assertEqual(self.calls,[('add',.5)])
    def test_bad_minimum_metadata(self):
        self.n.attr.definitions['weapon_min_reload_time'].Value.Property.PropertyPath='ReloadTime';self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_original_base_disagreement(self):
        self.a._values['BaseValue']=4.;self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_bad_selection(self):
        for value in (1.,.1,4.,float('nan')):
            with self.assertRaises(ValueError):self.make(value)
    def test_dispatch_routes_only_to_isolated_trial(self):
        m=self.n.base.m;calls=[];m.begin_blackboard_reward=lambda *args:calls.append(args)
        m.execute_activation(m.RELOAD_TRIAL_KEY,2.)
        self.assertEqual(calls,[(m.RELOAD_TRIAL_KEY,2.)]);self.assertNotIn(m.RELOAD_TRIAL_KEY,m.AUTO_OPTIONS)
    def test_permission_lost_before_add(self):
        self.assertTrue(self.lane.begin());self.allowed=False;self.tick();self.assertFalse(self.calls)
    def test_no_minimum_write_target(self):
        with self.assertRaises(ValueError):self.R.trial_amount('weapon_min_reload_time',2.)
        with self.assertRaises(ValueError):self.R.NativeRateTrial(self.R.RELOAD_MODE,self.binding,None,None,None,None,None,None,selection=2.,continuous=True)
