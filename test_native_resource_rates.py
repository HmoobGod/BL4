"""Synthetic native rate metadata, dispatch, cleanup, and F8 queue tests."""
import unittest
from enum import IntEnum
from test_foundation import Test
from test_combat_r13 import Node, desc
from test_double_jump_r52 import p,t

class Modifier(IntEnum):
    PostAdd=2
    ScaleMultiply=3
class Result(IntEnum):
    Success=0
    Failure=1
class FGbxDefPtr(Node):
    def __init__(self,name,typ,qualified=True):
        row=typ.definitions[name]
        super().__init__(_name=name,_type=typ,Context=row.Context,Value=row.Value)
        self._token=row._get_address()
    def _get_address(self):return self._token
class WrappedStruct(Node):pass
class NativeRateTests(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown)
        from bl4_custom_foundation import native_resource_rates as R
        self.R=R;self.mode='health';self.now=0.;self.tid=1;self.allowed=True;self.msg=[];self.native=[]
        self.pc,self.pawn,self.world=Node(),Node(),Node();self.key=('original pool',)
        self.rate=0.;self.base_rate=0.;self.apply=True;self.restore=True;self.echo=True;self.readback=None
        self.attr=t('GbxAttributeDef',R.DEF,p('Context','ZGbxInlineStructProperty'),p('Value','ZGbxInlineStructProperty'))
        self.handle_type=t('GbxAttributeModifierHandle',R.HANDLE)
        self.attr.definitions={}
        self.mod_enum=Node(Name=R.MOD_ENUM,_as_py=lambda:Modifier)
        self.res_enum=Node(Name=R.RESULT_ENUM,_as_py=lambda:Result)
        self.functions=[]
        for mode in R.TARGETS:self.create_def(mode)
        for name,sig in R.SPECS.items():
            ps=[p(n,k) for n,k in sig]
            if name!='RemoveAttributeModifier':ps[1].PropertyClass=Node(Name='/Script/CoreUObject.Object')
            if name=='AddModifierToGbxAttribute':ps[0].Struct=self.attr;ps[2].Enum=self.mod_enum;ps[5].Enum=self.res_enum;ps[6].Struct=self.handle_type
            if name=='RemoveAttributeModifier':ps[0].Struct=self.handle_type
            fn=Node(Name=name,NumParams=len(ps),_properties=lambda ps=ps:ps,Outer=Node(Name=R.LIB[:-1]),_path_name=lambda n=name:R.LIB+n)
            self.functions.append(fn)
        self.binding=self.bind()
    def create_def(self,mode):
        R=self.R;name,field,ctx,selector,_,_=R.TARGETS[mode]
        elem=t('ParsedPropertyPathElement','/Script/GbxCore.ParsedPropertyPathElement',p('PropertyName','ZNameProperty'),p('bUsesArrayIndex','ZBoolProperty'))
        pp=p('ParsedPath','ZStructProperty',Struct=elem);pp.ArrayDim=5
        parsed=t('ParsedProperty',R.PARSED,p('PropertyPath','ZStrProperty'),p('ParsedPathLength','ZUInt32Property'),pp)
        val=Node(_type=t('PropertyValueResolver',R.VALUE,p('PropertySupportsModifierRemoval','ZBoolProperty'),p('ResolvedType','ZEnumProperty'),desc('Property',parsed)),PropertySupportsModifierRemoval=True,ResolvedType=Node(name='Float'),Property=Node(_type=parsed,PropertyPath=field,ParsedPathLength=1,ParsedPath=[Node(_type=elem,PropertyName=field,bUsesArrayIndex=False)]))
        if mode=='health':
            c=Node(_type=t('GameResourcePoolContextResolver',ctx,p('ResourceDef','ZGameDataHandleProperty',TypeHandle=5)),ResourceDef=Node(_name='Health',_type_handle=5))
        else:
            c=Node(_type=t('OakActionSkillResourcePoolResolver',ctx,p('PoolType','ZEnumProperty',Enum=Node(Name='/Script/OakGame.EOakActionSkillResourcePoolType'))),PoolType=Node(name=selector))
        self.attr.definitions[name]=Node(Context=c,Value=val)
    def existing(self,fs,path,sig):
        return {'GetValueOfAttribute':self.get,'AddModifierToGbxAttribute':self.add,'RemoveAttributeModifier':self.remove}[path.rsplit(':',1)[1]]
    def bind(self):return self.R.NativeBinding(self.functions,self.existing,FGbxDefPtr,WrappedStruct)
    def get(self,name,pawn,default):
        self.assertEqual(name,self.R.TARGETS[self.mode][0]);self.assertIs(pawn,self.pawn)
        if self.readback:return self.readback()
        return self.rate
    def add(self,d,pawn,m,a,refresh,result):
        self.assertIs(pawn,self.pawn);self.assertIs(refresh,True);self.assertEqual(result,Result.Failure)
        self.native.append(('add',d._name,m,a))
        if self.apply:self.rate=self.rate+a if m==Modifier.PostAdd else self.rate*a
        return WrappedStruct(_type=self.handle_type),d if self.echo else Node(),Result.Success
    def remove(self,h):
        self.assertIs(h._type,self.handle_type);self.native.append(('remove',))
        if self.restore:self.rate=self.base_rate
        return True,WrappedStruct(_type=self.handle_type)
    def resolve(self):
        d,k=self.binding.definition(self.mode)
        return (self.pc,self.pawn,self.world),(self.key,k),d
    def trial(self,mode='health',base=0.):
        self.mode=mode;self.rate=self.base_rate=base
        return self.R.NativeRateTrial(mode,self.binding,self.resolve,lambda x:lambda:x,lambda:self.now,lambda:self.tid,self.msg.append,lambda:self.allowed)
    def tick(self,lane,dt=.2,permit=True):self.now+=dt;lane.tick(permit)
    def cycle(self,mode,base,expected):
        lane=self.trial(mode,base);self.assertTrue(lane.begin());self.assertFalse(self.native)
        self.tick(lane);self.assertAlmostEqual(self.rate,expected);self.assertEqual(lane.phase,'active')
        lane.stop('restore');self.assertEqual(len(self.native),1);self.tick(lane);self.assertEqual(lane.phase,'verify')
        self.tick(lane);self.assertEqual(lane.phase,'done');self.assertFalse(lane.fault);self.assertAlmostEqual(self.rate,base);self.assertEqual(len(self.native),2)
    def test_health_from_zero(self):self.cycle('health',0.,.001)
    def test_cooldown_native(self):self.cycle('cooldown',3.,6.)
    def test_duration_native(self):self.cycle('duration',2.,1.)
    def test_duration_parsed_path_disagreement(self):
        lane=self.trial('duration',2.);self.attr.definitions[self.R.TARGETS['duration'][0]].Value.Property.ParsedPath[0].PropertyName='MaxValue'
        self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_wrong_health_resource(self):
        lane=self.trial();self.attr.definitions[self.R.TARGETS['health'][0]].Context.ResourceDef._name='Shield'
        self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_unsupported_removal(self):
        lane=self.trial();self.attr.definitions[self.R.TARGETS['health'][0]].Value.PropertySupportsModifierRemoval=False
        self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_array_path_rejected(self):
        lane=self.trial();self.attr.definitions[self.R.TARGETS['health'][0]].Value.Property.ParsedPath[0].bUsesArrayIndex=True
        self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_bad_rate(self):
        lane=self.trial('cooldown',0.);self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_missing_definition(self):
        lane=self.trial();del self.attr.definitions[self.R.TARGETS['health'][0]];self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_duplicate_native_function(self):
        self.functions.append(self.functions[0]);self.assertRaises(ValueError,self.bind)
    def test_wrong_native_handle_type(self):
        self.functions[-1]._properties()[0].Struct=t('Other',self.R.HANDLE);self.assertRaises(ValueError,self.bind)
    def test_permission_lost_before_add(self):
        lane=self.trial();self.assertTrue(lane.begin());self.allowed=False;self.tick(lane);self.assertFalse(self.native)
    def test_late_permission_loss(self):
        lane=self.trial();self.assertTrue(lane.begin())
        def read():self.allowed=False;return self.rate
        self.readback=read;self.tick(lane);self.assertFalse(self.native)
    def test_permission_withdrawal_restores(self):
        lane=self.trial();lane.begin();self.tick(lane);self.allowed=False;self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done');self.assertEqual(self.rate,0.)
    def test_expiry_restores(self):
        lane=self.trial();lane.begin();self.tick(lane);self.tick(lane,10.);self.tick(lane);self.assertEqual(lane.phase,'done');self.assertEqual(len(self.native),2)
    def test_no_readd(self):
        lane=self.trial();lane.begin();self.tick(lane);[self.tick(lane) for _ in range(15)];self.assertEqual(len(self.native),1)
    def test_no_effect_remove_then_fault(self):
        lane=self.trial();self.apply=False;lane.begin();self.tick(lane);self.tick(lane);self.assertTrue(lane.fault);self.assertEqual(len(self.native),2)
    def test_echo_mismatch_remove_then_fault(self):
        lane=self.trial();self.echo=False;lane.begin();self.tick(lane);self.tick(lane);self.assertTrue(lane.fault);self.assertEqual(self.rate,0.)
    def test_false_cleanup_readback(self):
        lane=self.trial();self.restore=False;lane.begin();self.tick(lane);lane.stop('restore');self.tick(lane);self.assertTrue(lane.fault);self.tick(lane);self.assertEqual(len(self.native),2)
    def test_delayed_cleanup_readback(self):
        lane=self.trial();lane.begin();self.tick(lane);lane.stop('restore');self.tick(lane);self.rate=.001;self.tick(lane);self.assertTrue(lane.fault)
    def test_pool_replaced_no_removal_against_wrong_pool(self):
        lane=self.trial();lane.begin();self.tick(lane);self.key=('replacement',);lane.stop('restore');self.tick(lane);self.assertTrue(lane.fault);self.assertEqual(len(self.native),1)
    def test_reentrant_stop_during_add(self):
        lane=self.trial();original=self.binding.calls['AddModifierToGbxAttribute']
        def add(*a):lane.stop('reentrant');lane.tick(True);return original(*a)
        self.binding.calls['AddModifierToGbxAttribute']=add;lane.begin();self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done');self.assertEqual(len(self.native),2)
    def test_uncertain_add_no_replay(self):
        lane=self.trial();self.binding.calls['AddModifierToGbxAttribute']=lambda *a:None;lane.begin();self.tick(lane);self.assertTrue(lane.fault);self.assertFalse(lane.begin())
    def test_unknown_remove_shape_no_retry(self):
        lane=self.trial();lane.begin();self.tick(lane);calls=[]
        self.binding.calls['RemoveAttributeModifier']=lambda *a:calls.append(a) or True
        lane.stop('restore');self.tick(lane);self.tick(lane);self.assertTrue(lane.fault);self.assertEqual(len(calls),1)
    def test_no_writes_before_explicit_activation(self):
        lane=self.trial();self.tick(lane);self.assertFalse(self.native)
    def test_f8_dispatch_selection(self):
        m=self.base.m;called=[];m.begin_native_resource_rate=lambda mode,selection:called.append((mode,selection))
        for mode in ('health','cooldown','duration'):m.execute_activation('native_rate_'+mode,2.)
        self.assertEqual(called,[('health',2.),('cooldown',2.),('duration',2.)])
        self.assertRaises(ValueError,m.execute_activation,'native_rate_health',6.)

    def local_health(self):
        from test_health_pulse_r17 import FGameDataHandle
        from test_combat_r13 import attr,typ,arraydesc
        from types import SimpleNamespace as N
        self.mode='health'
        hp=FGameDataHandle('HealthType_FleshMock','FleshRed','IsGeneric')
        hp._type_handle=5
        current,maximum,disabled=attr(50.),attr(100.),attr(0);disabled._type.Name='GbxAttributeInteger'
        layer=typ('HealthTypeState',p('HealthType','ZGameDataHandleProperty'),desc('SimpleCurrentHealth',current._type),desc('SimpleMaxHealth',maximum._type))
        flesh=Node(_type=layer,HealthType=hp,SimpleCurrentHealth=current,SimpleMaxHealth=maximum)
        hs=Node(_type=typ('OakCharacterHealthState',desc('HealingDisabled',disabled._type),arraydesc('HealthTypeStates',desc('inner',layer))),owner=self.pawn,bCurrentlyDead=False,HealingDisabled=disabled,HealthTypeStates=[flesh])
        self.pawn.Class=t('OakCharacter','/Script/OakGame.OakCharacter',desc('HealthState',hs._type),p('HealthCondition','ZEnumProperty',Enum=Node(Name='/Script/OakGame.ECharacterHealthCondition')))
        self.pawn.HealthCondition=N(name='Healthy');self.pawn.HealthState=hs
        res=FGameDataHandle('Health','FleshRed','IsGeneric');res._type_handle=5
        self.attr.definitions[self.R.TARGETS['health'][0]].Context.ResourceDef=res
        self.native_cur=50.;self.native_pct=.5
        ctx=lambda:(self.pc,self.pawn,self.world,self.allowed)
        readers=(lambda pawn,h:self.native_cur,lambda pawn,h:self.native_pct,5)
        return self.R.make_local_resolver('health',self.binding,ctx,FGameDataHandle,readers)
    def test_local_health_crosschecks_pool(self):
        self.resolve=self.local_health();lane=self.trial();self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(lane.phase,'active',self.msg);lane.stop('restore');self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done',self.msg)
    def test_local_health_wrong_native_ratio(self):
        self.resolve=self.local_health();self.native_pct=.7;lane=self.trial();self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_local_health_wrong_native_current(self):
        self.resolve=self.local_health();self.native_cur=40.;lane=self.trial();self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_local_health_native_rate_does_not_refill(self):
        self.resolve=self.local_health();lane=self.trial();self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(self.pawn.HealthState.HealthTypeStates[0].SimpleCurrentHealth.Value,50.)
    def skill_local(self,mode):
        self.pawn.Class=t('OakCharacter','/Script/OakGame.OakCharacter');self.skill=Node();self.script=Node();self.maxima=[100.,100.]
        rs=(Node(Name='cooldown'),Node(Name='duration'));self.scope=(self.pc,self.pawn,self.world,self.skill,self.script)
        def resolve(initial=False,refresh=False):
            self.assertTrue(initial and refresh);return self.scope,('skill resource layout',),Node(),rs,(.2,.8),None
        def maxv(ref,h):return self.maxima[rs.index(h)]
        reader=Node(resolve=resolve,api=(None,None,maxv,None))
        return self.R.make_local_resolver(mode,self.binding,lambda:(self.pc,self.pawn,self.world,True),object,skill_reader=reader)
    def test_skill_pool_max_pinned(self):
        self.resolve=self.skill_local('duration');lane=self.trial('duration',2.);self.assertTrue(lane.begin(),self.msg);self.maxima[1]=101.;self.tick(lane);self.assertFalse(self.native)
    def test_skill_foreign_context_refused(self):
        self.resolve=self.skill_local('cooldown');self.scope=(self.pc,Node(),self.world,self.skill,self.script);lane=self.trial('cooldown',2.);self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_skill_native_target_maximum_stays_unchanged(self):
        self.resolve=self.skill_local('cooldown');lane=self.trial('cooldown',2.);self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(self.maxima,[100.,100.]);self.assertEqual(self.rate,4.)
    def test_cleanup_original_skill_after_wrong_maximum_change(self):
        self.resolve=self.skill_local('duration');lane=self.trial('duration',2.)
        lane.cleanup_key=lambda k:self.R.original_pool_identity('duration',k)
        old_add=self.binding.calls['AddModifierToGbxAttribute'];old_remove=self.binding.calls['RemoveAttributeModifier']
        def add(*args):
            result=old_add(*args);self.maxima[1]=120.;return result
        def remove(*args):
            result=old_remove(*args);self.maxima[1]=100.;return result
        self.binding.calls['AddModifierToGbxAttribute']=add;self.binding.calls['RemoveAttributeModifier']=remove
        self.assertTrue(lane.begin());self.tick(lane);self.tick(lane)
        self.assertTrue(lane.fault);self.assertEqual([x[0] for x in self.native],['add','remove']);self.assertEqual(self.maxima,[100.,100.]);self.assertEqual(self.rate,2.)
    def test_conservative_target_bound(self):
        lane=self.trial('health',.1);self.assertFalse(lane.begin());self.assertFalse(self.native)
    def test_getter_outside_bounds_attempts_original_cleanup(self):
        lane=self.trial();self.assertTrue(lane.begin());old_add=self.binding.calls['AddModifierToGbxAttribute']
        def add(*a):h=old_add(*a);self.rate=1.;return h
        self.binding.calls['AddModifierToGbxAttribute']=add;self.tick(lane);self.tick(lane)
        self.assertTrue(lane.fault);self.assertEqual([x[0] for x in self.native],['add','remove']);self.assertEqual(self.rate,0.)

    def test_custom_native_rate_cycle(self):
        for mode,base,selection,target in [('health',0.,3.5,.0035),('cooldown',2.,3.5,7.),('duration',4.,4.,1.)]:
            self.native.clear();lane=self.trial(mode,base);lane.selection=selection
            self.assertTrue(lane.begin());self.tick(lane);self.assertAlmostEqual(self.rate,target)
            lane.stop('restore');self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done');self.assertAlmostEqual(self.rate,base)
    def test_custom_rate_invalid(self):
        for mode,selection in [('health',False),('health',6.),('cooldown',1.),('duration',float('nan'))]:
            with self.assertRaises(ValueError):self.R.trial_amount(mode,selection)
    def test_native_rate_options_default_inert(self):
        m=self.base.m
        self.assertEqual(set(m.NATIVE_RATE_OPTIONS),{'health','cooldown','duration'})
        self.assertTrue(all(o.value==1. for o in m.NATIVE_RATE_OPTIONS.values()))
        self.assertFalse(self.native)
