"""Synthetic independent gun blackboard and gear luck admission/lifecycle tests."""
import unittest
from test_blackboard_rewards import RewardTests
from test_native_resource_rates import NativeRateTests, FGbxDefPtr, WrappedStruct, Modifier, Result
from test_combat_r13 import Node, desc, arraydesc
from test_double_jump_r52 import p,t

class GunTests(RewardTests):
    def setUp(self):
        super().setUp(); R=self.R; self.values[R.GUN_KEY]=('Float',1.)
        self.defs.definitions[R.GUN_KEY]=Node(Context=Node(_type=t('ActorContextResolver',R.ENGINE+'ActorContextResolver')),Value=Node(_type=self.val,Variable=self.key(R.GUN_KEY)))
        self.values[R.GUN_PEERS[0]]=('Float',1.)
        self.binding=R.GunBinding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
    def gun(self,scale=2.):
        return self.R.GunTrial(self.R.GUN_MODE,scale,self.binding,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def test_gun_roundtrip(self):
        l=self.gun();before=dict(self.values);self.assertTrue(l.begin());self.tick(l);self.assertEqual(self.values[l.name],('Float',2.));l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(self.values,before)
    def test_gun_reduction(self):
        l=self.gun(.5);self.assertTrue(l.begin());self.tick(l);self.assertEqual(self.values[l.name],('Float',.5));l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done')
    def test_gun_no_create(self):
        l=self.gun();del self.values[l.name];self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_gun_wrong_context(self):
        l=self.gun();self.defs.definitions[l.name].Context._type=self.ctx;self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_gun_board_replacement(self):
        l=self.gun();self.assertTrue(l.begin());self.tick(l);self.pawn.blackboard=Node(_type=self.pawn.blackboard._type);self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),1)
    def test_gun_join_cleanup(self):
        l=self.gun();self.assertTrue(l.begin());self.tick(l);self.ok=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done');self.assertEqual(self.values[l.name],('Float',1.))
    def test_gun_join_before_add(self):
        l=self.gun();self.assertTrue(l.begin());self.ok=False;self.tick(l);self.assertFalse(self.calls)
    def test_gun_peer_change(self):
        l=self.gun();self.assertTrue(l.begin());self.tick(l);self.values[self.R.GUN_PEERS[0]]=('Float',7.);self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[l.name],('Float',1.))
    def test_gun_unsupported_reward(self):
        with self.assertRaises(ValueError):self.binding.key(self.R.TARGETS['progress_money'])
    def test_gun_dispatch(self):
        m=self.base.m;calls=[];m.begin_blackboard_reward=lambda *args:calls.append(args);m.execute_activation(m.GUN_TRIAL_KEY,2.);self.assertEqual(calls,[(self.R.GUN_MODE,2.)]);self.assertNotIn(m.GUN_TRIAL_KEY,m.REWARD_KEYS)

class GearLuckTests(NativeRateTests):
    def setUp(self):
        super().setUp();from bl4_custom_foundation import luck_categories as L
        self.L=L;R=self.R
        self.cat_type=t('LuckCategoryDef',L.DEFINITION,p('CategoryType','ZEnumProperty',Enum=Node(Name=L.CATEGORY_ENUM)),p('ModifierType','ZEnumProperty',Enum=Node(Name=L.MODIFIER_ENUM)));self.cat_type.definitions={}
        def cat(name):
            self.cat_type.definitions[name]=Node(Context=None,Value=None);c=FGbxDefPtr(name,self.cat_type);c.CategoryType=Node(name='ModifiableAttribute');c.ModifierType=Node(name='ScaleMultiply');return c
        self.cat=cat('LuckCategory_Gear');self.peer=cat('Other')
        self.attr_type=t('GbxAttributeFloat', L.FLOAT,p('Value','ZFloatProperty'),p('BaseValue','ZFloatProperty'))
        self.entry_type=t('LuckCategoryAttribute',L.ENTRY,p('Category','ZGbxDefPtrProperty',Struct=self.cat_type),desc('Value',self.attr_type))
        self.state_type=t('LuckCategoryAttributesState',L.STATE,arraydesc('LuckCategories',desc('inner',self.entry_type)))
        self.entry=Node(_type=self.entry_type,Category=self.cat,Value=Node(_type=self.attr_type,Value=1.,BaseValue=1.));self.other=Node(_type=self.entry_type,Category=self.peer,Value=Node(_type=self.attr_type,Value=2.,BaseValue=2.))
        self.pc=Node(Class=t('OakPlayerController',L.PC,desc('LuckCategoryAttributesState',self.state_type)),LuckCategoryAttributesState=Node(_type=self.state_type,LuckCategories=[self.entry,self.other]),Pawn=self.pawn)
        self.pawn.Class=t('OakCharacter','/Script/OakGame.OakCharacter');self.pawn.Name='Pawn';self.eligible=True
        self.attr.definitions['att_luck_gear']=Node(Context=Node(_type=t('GbxPlayerControllerContextResolver',R.LUCK_CONTEXT)),Value=Node(_type=t('LuckCategoryValueResolver',R.LUCK_VALUE,p('Category','ZGbxDefPtrProperty',Struct=self.cat_type)),Category=self.cat))
        self.binding.calls['GetValueOfAttribute']=lambda name,owner,default:self.entry.Value.Value if name=='att_luck_gear' and owner is self.pc else default
        def add(d,owner,mod,amount,refresh,status):
            self.assertIs(owner,self.pc);self.assertEqual(mod,Modifier.ScaleMultiply);self.native.append(('add',amount));self.entry.Value.Value*=amount;return WrappedStruct(_type=self.handle_type),d,Result.Success
        def remove(h):self.native.append(('remove',));self.entry.Value.Value=1.;return True,WrappedStruct(_type=self.handle_type)
        self.binding.calls['AddModifierToGbxAttribute']=add;self.binding.calls['RemoveAttributeModifier']=remove
    def gear(self,scale=2.):
        R=self.R;mode=R.LUCK_MODE;resolver=R.make_local_resolver(mode,self.binding,lambda:(self.pc,self.pawn,self.world,self.eligible),None)
        return R.NativeRateTrial(mode,self.binding,resolver,lambda x:lambda:x,lambda:self.now,lambda:self.tid,self.msg.append,lambda:self.allowed,lambda k:R.original_pool_identity(mode,k),selection=scale)
    def test_gear_cycle(self):
        l=self.gear(3.);self.assertTrue(l.begin());self.tick(l);self.assertEqual(self.entry.Value.Value,3.);self.assertEqual(self.other.Value.Value,2.);l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(self.entry.Value.Value,1.)
    def test_gear_category_wrong(self):
        self.cat._name='OtherGear';self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_formula_rejected(self):
        self.cat.CategoryType=Node(name='Formula');self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_wrong_modifier(self):
        self.cat.ModifierType=Node(name='PostAdd');self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_getter_mismatch(self):
        self.binding.calls['GetValueOfAttribute']=lambda *_:2.;self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_zero(self):
        self.entry.Value.Value=0.;self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_missing(self):
        self.pc.LuckCategoryAttributesState.LuckCategories.remove(self.entry);self.assertFalse(self.gear().begin());self.assertFalse(self.native)
    def test_gear_reorder(self):
        l=self.gear();self.assertTrue(l.begin());self.pc.LuckCategoryAttributesState.LuckCategories.reverse();self.tick(l);self.assertEqual(l.phase,'active');l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done')
    def test_gear_peer_drift_cleanup(self):
        l=self.gear();self.assertTrue(l.begin());self.tick(l);self.other.Value.Value=3.;self.tick(l,.4);self.assertTrue(l.fault);self.assertEqual(self.native,[('add',2.),('remove',)])
    def test_gear_join_cleanup(self):
        l=self.gear();self.assertTrue(l.begin());self.tick(l);self.eligible=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done')
    def test_gear_replacement_no_remove(self):
        l=self.gear();self.assertTrue(l.begin());self.tick(l);self.pc.LuckCategoryAttributesState.LuckCategories[0]=Node(**vars(self.entry));self.tick(l,.4);self.assertTrue(l.fault);self.assertEqual(self.native,[('add',2.)])
    def test_gear_scale_bound(self):
        for value in (1,11,True,float('nan')):
            with self.assertRaises(ValueError):self.gear(value)
    def test_gear_dispatch(self):
        m=self.base.m;calls=[];m.begin_native_resource_rate=lambda *args:calls.append(args);m.execute_activation('native_rate_gear_luck',2.);self.assertEqual(calls,[('gear_luck',2.)]);self.assertNotIn('overall_loot_luck',m.AUTO_OPTIONS)
