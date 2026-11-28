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
        if ctx==R.HEALTH_CONTEXT:
            c=Node(_type=t('GameResourcePoolContextResolver',ctx,p('ResourceDef','ZGameDataHandleProperty',TypeHandle=5)),ResourceDef=Node(_name=selector,_type_handle=5))
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
        rs=(Node(Name='cooldown',_name='cooldown'),Node(Name='duration',_name='duration'));self.scope=(self.pc,self.pawn,self.world,self.skill,self.script)
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
        self.assertEqual(set(m.NATIVE_RATE_OPTIONS),{'health','cooldown','duration','vaultregen','vaultdelay','vaultdepleted','shieldpassive','gear_luck','cash','eridium','melee','gun_actor','shield_idle_rate','shield_idle_delay'})
        self.assertTrue(all(o.value==1. for o in m.NATIVE_RATE_OPTIONS.values()))
        self.assertFalse(self.native)

    def persistent_trial(self,mode='health',base=0.):
        lane=self.trial(mode,base);lane.continuous=True;lane.selection=2.
        return lane

    def test_persistent_native_rate_survives_manual_deadline(self):
        lane=self.persistent_trial();self.assertTrue(lane.begin());self.tick(lane);self.tick(lane,60.)
        self.assertEqual(lane.phase,'active');self.assertEqual(len(self.native),1)
        lane.stop('master off');self.tick(lane,permit=False);self.tick(lane,permit=False)
        self.assertEqual(lane.phase,'done');self.assertEqual(self.rate,0.);self.assertEqual(len(self.native),2)

    def test_persistent_native_rates_default_off(self):
        m=self.base.m
        self.assertEqual(set(m.NATIVE_AUTO_OPTIONS),{'native_rate_health','native_rate_cooldown','native_rate_duration','native_rate_vaultregen','native_rate_vaultdelay','native_rate_vaultdepleted','native_rate_shieldpassive','native_rate_gear_luck','native_rate_cash','native_rate_eridium','native_rate_melee','native_rate_gun_actor','native_rate_shield_idle_rate','native_rate_shield_idle_delay'})
        self.assertTrue(all(o.value is False for o in m.NATIVE_AUTO_OPTIONS.values()))

    def test_persistent_native_skill_and_refill_mutually_exclusive(self):
        m=self.base.m;k='native_rate_duration';m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['duration'].value=2.
        self.assertTrue(m.native_rate_allowed(k,2.));self.assertFalse(m.native_rate_allowed(k,3.))
        m.AUTOMATION_OPTIONS['skill_duration'].value=True
        self.assertFalse(m.native_rate_allowed(k,2.));self.assertIn('choose native',m.recovery_conflict('skill_duration'))
        m.AUTOMATION_OPTIONS['skill_duration'].value=False
        self.assertTrue(m.native_rate_allowed(k,2.))

    def test_persistent_native_rate_cleanup_survives_master_off(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['health'].value=2.
        self.assertTrue(lane.begin());self.tick(lane);m._automation_leases[k]=lane;m._automation_attempted.add(k)
        m.automation_permitted=lambda:False;m.stop_automation('master off')
        self.assertIs(m._automation_leases[k],lane);self.assertEqual(len(self.native),1)
        self.now+=.2;m.automation_tick();self.assertEqual(lane.phase,'verify');self.assertIs(m._automation_leases[k],lane)
        self.now+=.2;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertEqual(len(self.native),2);self.assertEqual(self.rate,0.)

    def test_permission_exception_drains_native_handle(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();lane.begin();self.tick(lane)
        m._automation_leases[k]=lane;m._automation_attempted.add(k)
        def broken():raise RuntimeError('permission reflection unavailable')
        m.automation_permitted=broken
        self.now+=.2;m.automation_tick();self.assertEqual(lane.phase,'verify');self.assertEqual(self.rate,0.)
        self.now+=.2;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertEqual(len(self.native),2)

    def test_permission_exception_cancels_armed_rate_without_dispatch(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();lane.begin();m._automation_leases[k]=lane
        def broken():raise RuntimeError('permission reflection unavailable')
        m.automation_permitted=broken
        self.now+=.2;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertFalse(self.native)
        self.assertIn(k,m._automation_attempted)

    def test_permission_exception_preserves_failed_cleanup_fault(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();lane.begin();self.tick(lane);m._automation_leases[k]=lane
        def broken():raise RuntimeError('permission reflection unavailable')
        m.automation_permitted=broken;self.restore=False
        self.now+=.2;m.automation_tick();self.assertTrue(lane.fault);self.assertIs(m._automation_leases[k],lane)
        self.now+=.2;m.automation_tick();self.assertEqual(len(self.native),2)

    def test_persistent_rate_selection_change_restores_no_rearm(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['health'].value=2.
        lane.begin();self.tick(lane);m._automation_leases[k]=lane;m._automation_attempted.add(k)
        m.automation_permitted=lambda:True;m.NATIVE_RATE_OPTIONS['health'].value=3.
        self.now+=.2;m.automation_tick();self.assertEqual(lane.phase,'verify')
        self.now+=.2;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertIn(k,m._automation_attempted);self.assertEqual(len(self.native),2)

    def test_native_rate_cleanup_fault_retained(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();lane.begin();self.tick(lane);m._automation_leases[k]=lane
        m.automation_permitted=lambda:False;self.restore=False
        self.now+=.2;m.automation_tick();self.assertTrue(lane.fault);self.assertIs(m._automation_leases[k],lane);self.assertTrue(m.automation_fault())

    def test_native_health_blocks_conflicting_field_until_restored(self):
        m=self.base.m;k='native_rate_health';lane=self.persistent_trial();lane.begin();self.tick(lane)
        m._automation_leases[k]=lane;m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['health'].value=2.
        m.AUTO_OPTIONS['healing_received'].value=True;m._PREVIEW_BY_KEY['healing_received'].value=2.
        self.assertNotIn('healing_received',m.auto_desired());self.assertFalse(m.native_rate_allowed(k,2.))
        m.automation_permitted=lambda:True;self.now+=.2;m.automation_tick()
        self.assertNotIn('healing_received',m.auto_desired());self.now+=.2;m.automation_tick()
        self.assertEqual(m.auto_desired()['healing_received'],2.)

    def test_native_cooldown_and_duration_independently_selected(self):
        m=self.base.m
        for mode in ('health','cooldown','duration'):
            m.NATIVE_AUTO_OPTIONS['native_rate_'+mode].value=True;m.NATIVE_RATE_OPTIONS[mode].value=2.
        self.assertTrue(all(m.native_rate_allowed('native_rate_'+k,2.) for k in ('health','cooldown','duration')))
        m.NATIVE_AUTO_OPTIONS['native_rate_cooldown'].value=False
        self.assertFalse(m.native_rate_allowed('native_rate_cooldown',2.));self.assertTrue(m.native_rate_allowed('native_rate_duration',2.))

    def test_three_native_lanes_arm_and_independently_restore(self):
        from types import SimpleNamespace as N
        m=self.base.m;lanes={};rates={};events=[]
        from unittest.mock import patch
        import sys
        mock=patch.dict(sys.modules,{'unrealsdk':N()});mock.start();self.addCleanup(mock.stop)
        m.time=N(monotonic=lambda:self.now)
        m.automation_permitted=lambda:True;m.bound_session=lambda sdk:None
        m.current_session=lambda _: (self.pc,self.pawn,self.world,True)
        def factory(kind,session):
            mode=kind.rsplit('_',1)[1];rates[mode]=0. if mode=='health' else 4.;base=rates[mode]
            def add(md,d,pawn,selection):
                events.append((md,'add'));amount=self.R.trial_amount(md,selection)
                rates[md]=base+amount if md=='health' else base*amount
                return object(),True
            def remove(handle):events.append((mode,'remove'));rates[mode]=base
            binding=N(read=lambda md,pawn:rates[md],add=add,remove=remove)
            lane=self.R.NativeRateTrial(mode,binding,lambda:((self.pc,self.pawn,self.world),(mode,),object()),lambda x:lambda:x,lambda:self.now,lambda:self.tid,self.msg.append,lambda:m.native_rate_allowed(kind,2.),selection=2.,continuous=True)
            lanes[kind]=lane;return lane
        m.make_automation_lane=factory
        for mode in ('health','cooldown','duration'):
            m.NATIVE_AUTO_OPTIONS['native_rate_'+mode].value=True;m.NATIVE_RATE_OPTIONS[mode].value=2.
        for _ in range(5):self.now+=.3;m.automation_tick()
        self.assertEqual(set(lanes),{'native_rate_health','native_rate_cooldown','native_rate_duration'});self.assertTrue(all(l.phase=='active' for l in lanes.values()))
        self.assertEqual(rates,{'health':.002,'cooldown':8.,'duration':2.})
        m.NATIVE_AUTO_OPTIONS['native_rate_cooldown'].value=False
        for _ in range(2):self.now+=.3;m.automation_tick()
        self.assertEqual(rates,{'health':.002,'cooldown':4.,'duration':2.})
        self.assertEqual(set(m._automation_leases),{'native_rate_health','native_rate_duration'})
        self.assertEqual(events.count(('cooldown','add')),1)
        m.stop_automation('master off');m.automation_permitted=lambda:False
        for _ in range(2):self.now+=.3;m.automation_tick()
        self.assertEqual(rates,{'health':0.,'cooldown':4.,'duration':4.});self.assertFalse(m._automation_leases)

    def edited_lane(self,mode='health',base=0.):
        m=self.base.m;k='native_rate_'+mode;lane=self.persistent_trial(mode,base)
        m.auto_master.value=True;m.auto_consent.value=True
        m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS[mode].value=2.
        m.automation_permitted=lambda:True
        lane.can_add=lambda:m.native_rate_allowed(k,lane.selection)
        lane.begin();self.tick(lane);m._automation_leases[k]=lane;m._automation_attempted.add(k)
        return m,k,lane

    def edit_rate(self,m,mode,value):
        m.queue_auto_edit(m.NATIVE_RATE_OPTIONS[mode],value);m.flush_auto_edits(force=True)

    def advance_rate(self,m):
        self.now+=.3;m.automation_tick()

    def test_saved_health_edit_replaces_only_after_delayed_restore(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.)
        self.assertEqual(lane.next_selection,3.);self.advance_rate(m)
        self.assertEqual(lane.phase,'verify');self.assertEqual(self.rate,0.);self.assertEqual(len(self.native),2)
        self.advance_rate(m);self.assertEqual(lane.phase,'armed');self.assertEqual(len(self.native),2)
        self.advance_rate(m);self.assertEqual(lane.phase,'active');self.assertAlmostEqual(self.rate,.003);self.assertEqual(len(self.native),3)
        m.stop_automation('restore');self.advance_rate(m);self.advance_rate(m)
        self.assertEqual(self.rate,0.);self.assertEqual(len(self.native),4)

    def test_saved_skill_rate_edit_updates_inverse_duration(self):
        m,k,lane=self.edited_lane('duration',4.);self.edit_rate(m,'duration',4.)
        for _ in range(3):self.advance_rate(m)
        self.assertEqual(lane.phase,'active');self.assertEqual(self.rate,1.);self.assertEqual(len(self.native),3)

    def test_edit_coalesces_during_cleanup(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.);self.advance_rate(m)
        self.edit_rate(m,'health',4.);self.advance_rate(m);self.advance_rate(m)
        self.assertAlmostEqual(self.rate,.004);self.assertEqual(len(self.native),3)

    def test_permission_loss_cancels_replacement(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.);self.advance_rate(m)
        m.automation_permitted=lambda:False;self.advance_rate(m)
        self.assertNotIn(k,m._automation_leases);self.assertEqual(len(self.native),2)

    def test_restore_all_cancels_replacement(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.);self.advance_rate(m)
        m.stop_automation('restore all');self.advance_rate(m)
        self.assertNotIn(k,m._automation_leases);self.assertEqual(len(self.native),2)

    def test_delayed_drift_blocks_replacement(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.);self.advance_rate(m)
        self.rate=.002;self.advance_rate(m)
        self.assertTrue(lane.fault);self.assertEqual(len(self.native),2)

    def test_failed_save_does_not_request_replacement(self):
        m,k,lane=self.edited_lane();m.mod.fail_save=True;self.edit_rate(m,'health',3.)
        self.assertIsNone(lane.next_selection);self.assertEqual(m.NATIVE_RATE_OPTIONS['health'].value,2.)

    def test_neutral_skill_edit_restores_without_replacement(self):
        m,k,lane=self.edited_lane('cooldown',4.);self.edit_rate(m,'cooldown',1.)
        self.advance_rate(m);self.advance_rate(m);self.assertNotIn(k,m._automation_leases)
        self.assertEqual(self.rate,4.);self.assertEqual(len(self.native),2)

    def test_rearm_refuses_replacement_scope_after_verified_cleanup(self):
        m,k,lane=self.edited_lane();original=lane.record
        lane.stop('restore');self.tick(lane,permit=False);self.tick(lane,permit=False)
        self.assertEqual(lane.phase,'done');self.key=('replacement pool',)
        m.NATIVE_RATE_OPTIONS['health'].value=3.
        self.assertFalse(lane.rearm_verified(original,3.));self.assertIsNone(lane.record)
        self.assertEqual(len(self.native),2)

    def test_saved_edit_cannot_replay_failed_cleanup(self):
        m,k,lane=self.edited_lane();self.edit_rate(m,'health',3.);self.restore=False
        self.advance_rate(m);self.advance_rate(m)
        self.assertTrue(lane.fault);self.assertEqual(len(self.native),2)

    def missing_health_trial(self,base=0.):
        self.local_health()
        ordinary=self.attr.definitions[self.R.TARGETS['health'][0]]
        missing=self.attr.definitions[self.R.TARGETS['missing_health'][0]]
        missing.Context.ResourceDef=ordinary.Context.ResourceDef
        self.peer_rate=.012
        from test_health_pulse_r17 import FGameDataHandle
        readers=(lambda pawn,h:self.native_cur,lambda pawn,h:self.native_pct,5)
        self.resolve=self.R.make_local_resolver('missing_health',self.binding,lambda:(self.pc,self.pawn,self.world,self.allowed),FGameDataHandle,readers)
        self.binding.calls['GetValueOfAttribute']=lambda name,pawn,default:self.peer_rate if name==self.R.TARGETS['health'][0] else self.get(name,pawn,default)
        lane=self.trial('missing_health',base)
        lane.cleanup_key=lambda k:self.R.original_pool_identity('missing_health',k)
        return lane

    def test_missing_health_exact_distinct_target(self):
        lane=self.missing_health_trial();self.assertTrue(lane.begin(),self.msg);self.tick(lane)
        self.assertEqual(lane.phase,'active',self.msg)
        self.assertEqual(self.native,[('add','health_resource_passive_missing_pct_regen',Modifier.PostAdd,.001)])
        self.assertEqual(self.peer_rate,.012)
        self.assertEqual(self.pawn.HealthState.HealthTypeStates[0].SimpleCurrentHealth.Value,50.)
        lane.stop('restore');self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,0.);self.assertEqual(self.peer_rate,.012)

    def test_missing_health_existing_positive_rate(self):
        lane=self.missing_health_trial(.02);lane.selection=3.5;self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertAlmostEqual(self.rate,.0235)
        self.tick(lane,10.);self.tick(lane);self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,.02)

    def test_missing_health_reject_flat_property_alias(self):
        lane=self.missing_health_trial();d=self.attr.definitions[self.R.TARGETS['missing_health'][0]];d.Value.Property.PropertyPath='PassivePercentRegenerationRate'
        self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_requires_exact_ordinary_peer(self):
        lane=self.missing_health_trial();del self.attr.definitions[self.R.TARGETS['health'][0]];self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_reject_peer_resource_mismatch(self):
        lane=self.missing_health_trial();d=self.attr.definitions[self.R.TARGETS['health'][0]];d.Context.ResourceDef=Node(_name='Health',_type_handle=5)
        self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_peer_drift_before_dispatch(self):
        lane=self.missing_health_trial();self.assertTrue(lane.begin());self.peer_rate=.02;self.tick(lane);self.assertEqual(self.native,[])

    def test_missing_health_peer_drift_after_dispatch_cleans_original(self):
        lane=self.missing_health_trial();self.assertTrue(lane.begin());self.tick(lane);self.peer_rate=.02;self.tick(lane,.3);self.assertEqual([v[0] for v in self.native],['add','remove']);self.assertTrue(lane.fault);self.assertEqual(self.rate,0.);self.assertEqual(self.peer_rate,.02)

    def test_missing_health_peer_invalid_rate(self):
        lane=self.missing_health_trial();self.peer_rate=float('nan');self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_pool_ratio_mismatch(self):
        lane=self.missing_health_trial();self.native_pct=.8;self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_no_continuous_mode(self):
        lane=self.missing_health_trial()
        with self.assertRaises(ValueError):self.R.NativeRateTrial('missing_health',self.binding,self.resolve,lambda x:lambda:x,lambda:self.now,lambda:self.tid,self.msg.append,lambda:True,continuous=True)

    def test_missing_health_over_bound(self):
        lane=self.missing_health_trial(.1);self.assertFalse(lane.begin());self.assertEqual(self.native,[])

    def test_missing_health_routes_existing_selection(self):
        m=self.base.m;calls=[];m.begin_native_resource_rate=lambda mode,selection:calls.append((mode,selection));m.execute_activation('native_rate_missing_health',2.4)
        self.assertEqual(calls,[('missing_health',2.4)]);self.assertNotIn('native_rate_missing_health',m.NATIVE_AUTO_OPTIONS)
        with self.assertRaises(ValueError):m.execute_activation('native_rate_missing_health',6.)

    def test_missing_health_permission_lost_before_dispatch(self):
        lane=self.missing_health_trial();self.assertTrue(lane.begin());self.allowed=False;self.tick(lane);self.assertEqual(self.native,[])

    def test_missing_health_peer_unavailable_after_dispatch_cleans_original(self):
        lane=self.missing_health_trial();self.assertTrue(lane.begin());self.tick(lane);del self.attr.definitions[self.R.TARGETS['health'][0]]
        self.tick(lane,.3);self.assertEqual([v[0] for v in self.native],['add','remove']);self.assertTrue(lane.fault);self.assertEqual(self.rate,0.)

    def shield_pool_trial(self,mode='shield_idle_rate',base=10.,selection=2.):
        self.local_health()
        from test_health_pulse_r17 import FGameDataHandle
        from test_shield_rates_r37 import ShieldRates
        self.p=self.pawn
        self.member=lambda *a,**kw:ShieldRates.member(self,*a,**kw)
        self.shield=ShieldRates.make_shield(self)
        layer=self.pawn.HealthState.HealthTypeStates[0]
        layer.HealthType=FGameDataHandle('HealthType_EnergyMock','EnergyBlue','IsShield');layer.HealthType._type_handle=5
        res=FGameDataHandle('Shield','EnergyBlue','IsShield');res._type_handle=5
        self.attr.definitions[self.R.TARGETS[mode][0]].Context.ResourceDef=res
        self.resolve=self.R.make_local_resolver(mode,self.binding,lambda:(self.pc,self.pawn,self.world,self.allowed),FGameDataHandle,(lambda pawn,h:self.native_cur,lambda pawn,h:self.native_pct,5),shield_getter=lambda pawn:self.shield)
        lane=self.trial(mode,base);lane.selection=selection;lane.cleanup_key=lambda key:self.R.original_pool_identity(mode,key)
        return lane

    def test_native_shield_pool_rate_cycle(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(lane.phase,'active',self.msg);self.assertEqual(self.rate,20.)
        self.assertEqual(self.shield.RegenRate.Value,10.);self.assertEqual(self.native,[('add','shield_resource_idle_regen_rate',Modifier.ScaleMultiply,2.)])
        lane.stop('restore');self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,10.)

    def test_native_shield_pool_delay_inverse(self):
        lane=self.shield_pool_trial('shield_idle_delay',4.,2.);self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(self.rate,2.);self.assertEqual(self.native,[('add','shield_resource_idle_regen_delay',Modifier.ScaleMultiply,.5)])
        self.tick(lane,10.);self.tick(lane);self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,4.)

    def test_native_shield_pool_slowdown(self):
        lane=self.shield_pool_trial('shield_idle_delay',4.,.5);self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.assertEqual(self.rate,8.)

    def test_native_shield_pool_reject_armor(self):
        lane=self.shield_pool_trial();self.shield.system='Armor';self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_reject_wrong_owner(self):
        lane=self.shield_pool_trial();self.shield.OwningCharacter=Node();self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_reject_wrong_resource(self):
        lane=self.shield_pool_trial();self.attr.definitions[self.R.TARGETS[self.mode][0]].Context.ResourceDef._name='Weapon_Shield';self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_reject_wrong_property(self):
        lane=self.shield_pool_trial();self.attr.definitions[self.R.TARGETS[self.mode][0]].Value.Property.ParsedPath[0].PropertyName='PassiveRegenerationRate';self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_reject_ratio_mismatch(self):
        lane=self.shield_pool_trial();self.native_pct=.6;self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_reject_current_mismatch(self):
        lane=self.shield_pool_trial();self.native_cur=40.;self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_pool_persistent_opt_in(self):
        lane=self.shield_pool_trial();lane=self.R.NativeRateTrial(self.mode,self.binding,self.resolve,lambda x:lambda:x,lambda:self.now,lambda:self.tid,self.msg.append,lambda:True,continuous=True)
        self.assertTrue(lane.begin());self.tick(lane);self.tick(lane,31.);self.assertEqual(lane.phase,'active');lane.stop('restore');self.tick(lane);self.tick(lane);self.assertEqual(lane.phase,'done')

    def test_native_shield_pool_reject_swap_before_dispatch(self):
        from test_shield_rates_r37 import ShieldRates
        lane=self.shield_pool_trial();self.assertTrue(lane.begin(),self.msg);self.shield=ShieldRates.make_shield(self);self.tick(lane);self.assertFalse(self.native)

    def test_native_shield_pool_lost_eligibility_restores_original(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin(),self.msg);self.tick(lane);self.allowed=False;self.tick(lane,permit=False);self.tick(lane,permit=False);self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,10.)

    def test_native_shield_pool_routes_existing_selection(self):
        m=self.base.m;calls=[];m.begin_native_resource_rate=lambda mode,selection:calls.append((mode,selection))
        for mode in ('shield_idle_rate','shield_idle_delay'):
            m.execute_activation('native_rate_'+mode,2.);self.assertFalse(m.NATIVE_AUTO_OPTIONS['native_rate_'+mode].value);self.assertRaises(ValueError,m.execute_activation,'native_rate_'+mode,1.)
        self.assertEqual(calls,[('shield_idle_rate',2.),('shield_idle_delay',2.)])

    def set_shield_charge(self,current,ratio=None):
        self.pawn.HealthState.HealthTypeStates[0].SimpleCurrentHealth.Value=current
        self.native_cur=current;self.native_pct=current/100 if ratio is None else ratio

    def test_native_shield_depletion_during_active_trial_restores(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin());self.tick(lane)
        self.set_shield_charge(0.);self.tick(lane,.3)
        self.assertEqual(lane.phase,'active',self.msg);self.assertEqual(len(self.native),1)
        lane.stop('restore while depleted');self.tick(lane);self.tick(lane)
        self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,10.)

    def test_native_shield_depletion_before_dispatch_after_positive_witness(self):
        lane=self.shield_pool_trial('shield_idle_delay',4.,2.);self.assertTrue(lane.begin())
        self.set_shield_charge(0.);self.tick(lane);self.assertEqual(lane.phase,'active',self.msg)
        self.set_shield_charge(25.);lane.stop('restore');self.tick(lane);self.tick(lane)
        self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,4.)

    def test_native_shield_initial_zero_still_refused(self):
        lane=self.shield_pool_trial();self.set_shield_charge(0.)
        self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_depleted_disagreeing_ratio_refused(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin());self.set_shield_charge(0.,.001)
        self.tick(lane);self.assertFalse(self.native)

    def test_native_shield_depleted_replacement_refused(self):
        from test_shield_rates_r37 import ShieldRates
        lane=self.shield_pool_trial();self.assertTrue(lane.begin());self.tick(lane)
        self.set_shield_charge(0.);self.shield=ShieldRates.make_shield(self)
        lane.stop('swap');self.tick(lane);self.assertTrue(lane.fault);self.assertEqual(len(self.native),1)


    def test_native_health_cleanup_during_ffyl(self):
        self.resolve=self.local_health();lane=self.trial();lane.cleanup_key=lambda k:self.R.original_pool_identity('health',k)
        self.assertTrue(lane.begin());self.tick(lane)
        self.pawn.HealthCondition=Node(name='Injured')
        self.pawn.HealthState.HealthTypeStates[0].SimpleCurrentHealth.Value=0.
        self.native_cur=self.native_pct=0.
        self.tick(lane,.3);self.tick(lane)
        self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,0.)
        self.assertEqual([v[0] for v in self.native],['add','remove'])

    def test_native_health_cleanup_healing_disabled(self):
        self.resolve=self.local_health();lane=self.trial();lane.cleanup_key=lambda k:self.R.original_pool_identity('health',k)
        self.assertTrue(lane.begin());self.tick(lane)
        self.pawn.HealthState.HealingDisabled.Value=1
        self.tick(lane,.3);self.tick(lane)
        self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,0.)

    def test_native_health_initial_ineligible_never_adds(self):
        self.resolve=self.local_health();lane=self.trial();self.pawn.HealthCondition=Node(name='Injured')
        self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_health_injury_during_native_read_blocks_add(self):
        self.resolve=self.local_health();lane=self.trial();self.assertTrue(lane.begin())
        old=self.binding.calls['GetValueOfAttribute']
        def injured(*a):
            self.pawn.HealthCondition=Node(name='Injured');return old(*a)
        self.binding.calls['GetValueOfAttribute']=injured
        self.tick(lane);self.assertFalse(self.native)

    def test_native_health_cleanup_rejects_replaced_layer(self):
        self.resolve=self.local_health();lane=self.trial();lane.cleanup_key=lambda k:self.R.original_pool_identity('health',k)
        self.assertTrue(lane.begin());self.tick(lane)
        layer=self.pawn.HealthState.HealthTypeStates[0]
        self.pawn.HealthState.HealthTypeStates[0]=Node(_type=layer._type,HealthType=layer.HealthType,SimpleCurrentHealth=layer.SimpleCurrentHealth,SimpleMaxHealth=layer.SimpleMaxHealth)
        self.pawn.HealthCondition=Node(name='Injured');self.tick(lane,.3)
        self.assertTrue(lane.fault);self.assertEqual(len(self.native),1)

    def test_native_shield_cleanup_during_ffyl(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin());self.tick(lane)
        self.pawn.HealthCondition=Node(name='Injured');self.set_shield_charge(0.)
        self.tick(lane,.3);self.tick(lane)
        self.assertEqual(lane.phase,'done',self.msg);self.assertEqual(self.rate,10.)
        self.assertEqual([v[0] for v in self.native],['add','remove'])

    def test_native_shield_initial_healing_disabled_never_adds(self):
        lane=self.shield_pool_trial();self.pawn.HealthState.HealingDisabled.Value=1
        self.assertFalse(lane.begin());self.assertFalse(self.native)

    def test_native_shield_same_handle_replacement_layer_refused(self):
        lane=self.shield_pool_trial();self.assertTrue(lane.begin());self.tick(lane)
        layer=self.pawn.HealthState.HealthTypeStates[0]
        self.pawn.HealthState.HealthTypeStates[0]=Node(_type=layer._type,HealthType=layer.HealthType,SimpleCurrentHealth=layer.SimpleCurrentHealth,SimpleMaxHealth=layer.SimpleMaxHealth)
        lane.stop('restore');self.tick(lane)
        self.assertTrue(lane.fault);self.assertEqual(len(self.native),1)
