"""Synthetic exact weapon context and modifier ownership; no real gunfire."""
import unittest
from test_native_resource_rates import NativeRateTests, Modifier, Result, WrappedStruct
from test_combat_r13 import Combat, Node, attr
from test_requested_damage import add_damage
from test_double_jump_r52 import p,t


class NativeWeaponDamageTests(unittest.TestCase):
    def setUp(self):
        self.n=NativeRateTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        from bl4_custom_foundation.native_weapon_damage import make_trial
        self.make_trial=make_trial;self.R=self.n.R
        self.w=self.c.w;self.pawn=self.c.p;self.pc=Node(Class=t('OakPlayerController','/Script/OakGame.OakPlayerController'),Pawn=self.pawn)
        self.pawn.Class._path_name=lambda:'/Script/OakGame.OakCharacter'
        self.pawn._path_name=lambda:'Test.PlayerPawn'
        self.w.Class._path_name=lambda:'/Script/OakGame.OakWeapon'
        self.fire=self.w.behaviors[0];self.a=add_damage(self.fire)
        firebase=t('WeaponBehavior_Fire',self.R.WEAPON_FIRE);self.fire.Class._superfields=lambda:iter((firebase,))
        row=self.n.attr.definitions['weapon_damage'];self.ctx=Node(_type=t('WeaponAttributeContextResolver',self.R.WEAPON_CONTEXT,p('BehaviorTypeToFurtherResolveTo','ZSoftClassProperty',MetaClass=t('WeaponBehavior','/Script/GbxWeapon.WeaponBehavior')),p('usemodebitmask','ZUInt32Property')),BehaviorTypeToFurtherResolveTo=firebase,usemodebitmask=0)
        row.Context=self.ctx;self.row=row;self.ok=True;self.allowed=True;self.native=[];self.read_override=None
        self.binding=self.n.binding
        self.binding.calls['GetValueOfAttribute']=self.get
        self.binding.calls['AddModifierToGbxAttribute']=self.add
        self.binding.calls['RemoveAttributeModifier']=self.remove
        self.lane=self.make_trial(self.binding,lambda:(self.pc,self.pawn,self.n.world,self.ok),lambda o:lambda:o,lambda:self.n.now,lambda:self.n.tid,self.n.msg.append,lambda:self.allowed,2.)
    def get(self,name,obj,default):
        self.assertEqual(name,'weapon_damage');self.assertIs(obj,self.w)
        return self.a.Value if self.read_override is None else self.read_override
    def add(self,d,obj,m,amount,refresh,result):
        self.assertIs(obj,self.w);self.assertEqual(m,Modifier.ScaleMultiply);self.assertIs(refresh,True)
        self.native.append('add');self.a._values['Value']*=amount
        return WrappedStruct(_type=self.n.handle_type),d,Result.Success
    def remove(self,h):
        self.native.append('remove');self.a._values['Value']=100.
        return True,WrappedStruct(_type=self.n.handle_type)
    def tick(self,dt=.3):self.n.now+=dt;self.lane.tick(True)
    def start(self):
        self.assertTrue(self.lane.begin(),self.n.msg);self.tick();self.assertEqual(self.lane.phase,'active',self.n.msg)
    def done(self):
        self.tick();self.tick();self.assertEqual(self.lane.phase,'done',self.n.msg);self.assertEqual(self.native,['add','remove']);self.assertEqual(self.a.Value,100.);self.assertEqual(self.a.BaseValue,100.);self.assertFalse(self.a.writes)
    def test_native_scale_and_restore(self):
        self.start();self.assertEqual(self.a.Value,200.);self.assertEqual(self.a.BaseValue,100.);self.w.CurrentState='Firing';self.tick();self.assertEqual(self.lane.phase,'active');self.lane.stop('test');self.done()
    def test_native_initial_readback_mismatch(self):
        self.read_override=99.;self.assertFalse(self.lane.begin());self.assertFalse(self.native)
    def test_native_wrong_class(self):
        self.ctx.BehaviorTypeToFurtherResolveTo=Node(Name=self.R.WEAPON_FIRE);self.assertFalse(self.lane.begin());self.assertFalse(self.native)
    def test_native_wrong_mask(self):
        self.ctx.usemodebitmask=2;self.assertFalse(self.lane.begin());self.assertFalse(self.native)
    def test_native_multiple_fire(self):
        self.w.behaviors.append(Node(Name='UM1_Fire',Class=self.fire.Class,Outer=self.w));self.assertFalse(self.lane.begin());self.assertFalse(self.native)
    def test_native_firing_before_dispatch(self):
        self.assertTrue(self.lane.begin());self.w.CurrentState='Firing';self.tick();self.assertFalse(self.native)
    def test_native_mode_change_removes_original(self):
        self.start();self.w.CurrentUseModeIndex=1;self.done()
    def test_native_join_cleanup(self):
        self.start();self.ok=False;self.done()
    def test_native_removed_weapon_no_wrong_cleanup(self):
        self.start();self.pawn.ActiveWeapons.Slots=[];self.tick();self.assertTrue(self.lane.fault);self.assertEqual(self.native,['add'])
    def test_native_base_changed_cleanup_fault(self):
        self.start();self.a._values['BaseValue']=110.;self.tick();self.assertTrue(self.lane.fault);self.assertEqual(self.native,['add','remove']);self.assertEqual(self.a.BaseValue,110.)
    def test_native_no_getter_effect_restores(self):
        self.assertTrue(self.lane.begin());self.read_override=100.;self.tick();self.tick();self.assertTrue(self.lane.fault);self.assertEqual(self.native,['add','remove'])

    def test_primary_admission_preserved(self):
        from bl4_custom_foundation.native_weapon_damage import choose_gun_trial
        lane=Node(begin=lambda:True);self.assertIs(choose_gun_trial(lambda:lane,lambda:self.fail('fallback called'),self.n.msg.append),lane)
    def test_fallback_after_no_dispatch_hold(self):
        from bl4_custom_foundation.native_weapon_damage import choose_gun_trial
        lane=Node(begin=lambda:False,record=None,fault=False,phase='idle',owned=False)
        self.assertIs(choose_gun_trial(lambda:lane,lambda:self.lane,self.n.msg.append),self.lane);self.assertEqual(self.lane.phase,'armed');self.assertFalse(self.native)
    def test_fallback_after_binding_unavailable(self):
        from bl4_custom_foundation.native_weapon_damage import choose_gun_trial
        def missing():raise ValueError('actor API unavailable')
        self.assertIs(choose_gun_trial(missing,lambda:self.lane,self.n.msg.append),self.lane);self.assertEqual(self.lane.phase,'armed')
    def test_no_fallback_after_dispatch(self):
        from bl4_custom_foundation.native_weapon_damage import choose_gun_trial
        lane=Node(begin=lambda:False,record=None,fault=True,phase='fault',owned=False)
        self.assertIs(choose_gun_trial(lambda:lane,lambda:self.fail('fallback called'),self.n.msg.append),lane)

    def test_armed_late_value_change_refuses_add(self):
        self.assertTrue(self.lane.begin());self.a._values['Value']=101.;self.tick();self.assertFalse(self.native);self.assertEqual(self.a.Value,101.)
    def test_armed_late_session_loss_refuses_add(self):
        self.assertTrue(self.lane.begin());original=self.lane.can_add
        def lose():
            self.ok=False
            return original()
        self.lane.can_add=lose;self.tick();self.assertFalse(self.native)
    def test_new_internal_module_has_no_game_imports(self):
        import ast
        from pathlib import Path
        path=Path(__file__).parent/'bl4_custom_foundation'/'native_weapon_damage.py'
        tree=ast.parse(path.read_text());self.assertFalse(any(isinstance(n,ast.Import) for n in ast.walk(tree)))
        self.assertEqual({n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)},{'native_resource_rates','gameplay_fields','weapon_rates'})
