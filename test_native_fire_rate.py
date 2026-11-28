"""Synthetic native FireRate modifier, original field and cleanup; no game execution."""
import unittest
from test_native_weapon_damage import NativeWeaponDamageTests
from test_native_resource_rates import Modifier, Result, WrappedStruct
from test_combat_r13 import Node

class NativeFireRateTests(unittest.TestCase):
    def setUp(self):
        self.f=NativeWeaponDamageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;self.R=f.R;self.a=f.c.fire;self.w=f.w;self.damage=f.a
        self.row=f.n.attr.definitions['weapon_fire_rate'];self.row.Context=f.ctx
        f.binding.calls.update(GetValueOfAttribute=self.get,AddModifierToGbxAttribute=self.add,RemoveAttributeModifier=self.remove)
        self.calls=[];self.override=None;self.lane=self.make(2.)
    def make(self,selection):
        from bl4_custom_foundation.native_weapon_damage import make_fire_rate_trial
        f=self.f
        return make_fire_rate_trial(f.binding,lambda:(f.pc,f.pawn,f.n.world,f.ok),lambda o:lambda:o,lambda:f.n.now,lambda:f.n.tid,f.n.msg.append,lambda:f.allowed,selection)
    def get(self,name,obj,default):
        self.assertEqual(name,'weapon_fire_rate');self.assertIs(obj,self.w)
        return self.a.Value if self.override is None else self.override
    def add(self,d,obj,m,amount,refresh,result):
        self.assertEqual(d._name,'weapon_fire_rate');self.assertIs(obj,self.w);self.assertEqual(m,Modifier.ScaleMultiply);self.assertIs(refresh,True)
        self.calls.append(('add',amount));self.a._values['Value']*=amount
        return WrappedStruct(_type=self.f.n.handle_type),d,Result.Success
    def remove(self,h):
        self.calls.append(('remove',));self.a._values['Value']=8.
        return True,WrappedStruct(_type=self.f.n.handle_type)
    def tick(self,dt=.3):self.f.n.now+=dt;self.lane.tick(True)
    def start(self):
        self.assertTrue(self.lane.begin(),self.f.n.msg);self.tick();self.assertEqual(self.lane.phase,'active',self.f.n.msg)
    def finish(self):
        self.tick();self.tick();self.assertEqual(self.lane.phase,'done',self.f.n.msg);self.assertEqual(self.a.Value,8.);self.assertEqual(self.a.BaseValue,8.);self.assertFalse(self.a.writes);self.assertEqual(self.damage.Value,100.);self.assertFalse(self.damage.writes)
    def test_native_fire_rate_only(self):
        self.start();self.assertEqual(self.a.Value,16.);self.w.CurrentState='Firing';self.tick();self.assertEqual(self.lane.phase,'active');self.lane.stop('test');self.finish();self.assertEqual(self.calls,[('add',2.),('remove',)])
    def test_slower_fire_rate(self):
        self.lane=self.make(.5);self.start();self.assertEqual(self.a.Value,4.);self.lane.stop('test');self.finish()
    def test_exact_parsed_rate(self):
        self.row.Value.Property.ParsedPath[0].PropertyName='Damage';self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_no_unequal_baseline(self):
        self.a._values['BaseValue']=7.;self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_native_mismatch(self):
        self.override=9.;self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_ambiguous_behavior(self):
        self.w.behaviors.append(Node(Name='UM1_ExtraFire',Class=self.f.fire.Class,Outer=self.w));self.assertFalse(self.lane.begin());self.assertFalse(self.calls)
    def test_busy_before_dispatch(self):
        self.assertTrue(self.lane.begin());self.w.CurrentState='Firing';self.tick();self.assertFalse(self.calls)
    def test_permission_loss_cleanup(self):
        self.start();self.f.ok=False;self.finish();self.assertEqual(self.calls,[('add',2.),('remove',)])
    def test_mode_change_cleanup(self):
        self.start();self.w.CurrentUseModeIndex=1;self.finish()
    def test_expiry(self):
        self.start();self.tick(31.);self.finish()
    def test_no_continuous_or_neutral(self):
        for value in (1.,.1,4.,float('nan'),True):
            with self.assertRaises(ValueError):self.make(value)
        with self.assertRaises(ValueError):self.R.NativeRateTrial(self.R.FIRE_RATE_MODE,self.f.binding,None,None,None,None,None,None,selection=2.,continuous=True)
    def test_isolated_routing(self):
        m=self.f.n.base.m;calls=[];m.begin_blackboard_reward=lambda *args:calls.append(args)
        m.execute_activation(m.FIRE_RATE_TRIAL_KEY,2.)
        self.assertEqual(calls,[(m.FIRE_RATE_TRIAL_KEY,2.)]);self.assertNotIn(m.FIRE_RATE_TRIAL_KEY,m.AUTO_OPTIONS)
