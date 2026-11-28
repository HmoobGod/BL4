"""Synthetic native-shaped getter and adaptive assist regression cases."""
import unittest
from types import SimpleNamespace as N
from test_recovery_r35 import PersistentSkill

class AdaptiveSkill(unittest.TestCase):
    def setUp(self):
        self.t=PersistentSkill();self.t.setUp();self.addCleanup(self.t.doCleanups)
        self.s=self.t.s;self.m=self.s.m;self.getters=[];self.override={}
        from bl4_custom_foundation.skill_pulse import ACTION
        for idx,mode in enumerate(('Cooldown','Duration')):
            for internal in (False,True):
                name='Get'+mode+'AsPercent'+('Internal' if internal else '')
                path=ACTION+name
                first=type('ZStructProperty' if internal else 'ZObjectProperty',(),{'Name':'ComponentReference' if internal else 'target','ArrayDim':1})()
                if internal:first.Struct=self.s.rt
                else:first.PropertyClass=N(_path_name=lambda:'/Script/OakGame.OakCharacter')
                props=[first,type('ZFloatProperty',(),{'Name':'ReturnValue','ArrayDim':1})()]
                cdo=N();owner=N(_path_name=lambda:ACTION[:-1],ClassDefaultObject=cdo)
                fn=N(Name=name,Outer=owner,NumParams=2,_path_name=lambda path=path:path,_properties=lambda props=props:props)
                def bound(arg,idx=idx,internal=internal,name=name):
                    self.assertIs(arg.Context if internal else arg,self.s.script if internal else self.s.p)
                    return self.override.get(name,self.s.val[idx])
                bound.func=fn;setattr(cdo,name,bound);self.s.funcs.append(fn);self.getters.append(fn)
    def arm(self,mode='cooldown',rate=2.,**kwargs):
        self.t.arm(mode,**{'adaptive_skill_'+mode:True,'adaptive_rate_skill_'+mode:rate},**kwargs)
        self.s.advance(dt=.2)
    def test_default_off(self):
        self.assertTrue(all(o.value is False for o in self.m.SKILL_ADAPTIVE.values()))
        self.assertTrue(all(o.value==1 for o in self.m.SKILL_RATES.values()))
    def test_cooldown_uses_smaller_delta(self):
        self.arm();self.s.advance(.21);self.s.advance(.23);self.assertAlmostEqual(self.s.calls[0][1],.01)
    def test_duration_scaled(self):
        self.arm('duration',3.);self.s.advance(d=.79);self.s.advance(d=.78);self.assertAlmostEqual(self.s.calls[0][1],.02)
    def test_hard_cap(self):
        self.arm(rate=3.);self.s.advance(.3);self.s.advance(.4);self.assertAlmostEqual(self.s.calls[0][1],.03)
    def test_one_x_no_refill(self):
        self.arm(rate=1.);self.s.advance(.3);self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_lag_no_catchup(self):
        self.arm();self.s.advance(.3,dt=5);self.s.advance(.31);self.assertEqual(self.s.calls,[]);self.s.advance(.32);self.assertAlmostEqual(self.s.calls[0][1],.01)
    def test_getter_mismatch_admission(self):
        self.override['GetCooldownAsPercentInternal']=.8;self.arm();self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_getter_mismatch_active(self):
        self.arm();self.s.advance(.3);self.override['GetCooldownAsPercent']=.8;self.s.advance(.4);self.assertEqual(self.s.calls,[]);self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_missing_getter(self):
        self.s.funcs.remove(self.getters[0]);self.arm();self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_signature_refused(self):
        self.getters[1]._properties()[0].ArrayDim=2;self.arm();self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_live_rate_resets_trend(self):
        self.arm();self.s.advance(.21);self.m.apply({'adaptive_rate_skill_cooldown':3.});self.s.advance(.22);self.s.advance(.23);self.assertEqual(self.s.calls,[]);self.s.advance(.24);self.assertAlmostEqual(self.s.calls[0][1],.02)
    def test_mode_change_stops_without_fallback(self):
        self.arm();self.s.advance(.3);self.m.set_auto_setting(self.m.SKILL_ADAPTIVE['skill_cooldown'],False);self.s.advance(.4);self.s.advance(.5);self.assertEqual(self.s.calls,[]);self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_own_sample_discarded(self):
        self.arm();self.s.advance(.21);self.s.advance(.22);self.s.advance(.25);self.s.advance(.26);self.assertEqual(len(self.s.calls),1);self.s.advance(.27);self.assertEqual(len(self.s.calls),2)
    def test_join_stops(self):
        self.arm();self.s.advance(.3);self.s.b.f.players=2;self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_mode_change_during_getter(self):
        self.arm();self.s.advance(.3);lease=self.m._automation_leases['skill_cooldown'];old=lease.adaptive_api[0]
        def read(*a):
            value=old(*a);self.m.apply({'adaptive_skill_cooldown':False});return value
        lease.adaptive_api=(read,lease.adaptive_api[1]);self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_rate_change_during_getter(self):
        self.arm();self.s.advance(.3);lease=self.m._automation_leases['skill_cooldown'];old=lease.adaptive_api[0]
        def read(*a):
            value=old(*a);self.m.apply({'adaptive_rate_skill_cooldown':1.});return value
        lease.adaptive_api=(read,lease.adaptive_api[1]);self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_slow_getter_no_dispatch(self):
        self.arm();self.s.advance(.3);lease=self.m._automation_leases['skill_cooldown'];old=lease.adaptive_api[0]
        def read(*a):
            value=old(*a);self.s.now+=.3;return value
        lease.adaptive_api=(read,lease.adaptive_api[1]);self.s.advance(.4);self.assertEqual(self.s.calls,[])

    def native_rate_fixture(self, mode):
        # Real F8 integration, real SkillPulse constructor / descriptor readers,
        # synthetic attribute modifier boundary (covered separately by native-rate tests).
        from unittest.mock import patch
        import importlib
        R=importlib.import_module(self.m.__package__+".native_resource_rates")
        self.s.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter'
        self.s.p._path_name=lambda:'/Game/Test.LocalPawn'
        self.s.b.f.sdk.unreal.FGbxDefPtr=object
        self.rate_value=2.;self.rate_calls=[];self.rate_definition=object();self.rate_handle=object()
        def read(m,pawn):
            self.assertEqual(m,mode);self.assertIs(pawn,self.s.p);return self.rate_value
        def add(m,d,pawn,selection):
            self.assertEqual(m,mode);self.assertIs(d,self.rate_definition);self.assertIs(pawn,self.s.p)
            self.rate_calls.append('add');self.rate_value=2.*R.trial_amount(m,selection);return self.rate_handle,True
        def remove(h):
            self.assertIs(h,self.rate_handle);self.rate_calls.append('remove');self.rate_value=2.
        fake=N(definition=lambda m:(self.rate_definition,('native definition',m)),read=read,add=add,remove=remove)
        patcher=patch.object(R,'NativeBinding',return_value=fake);patcher.start();self.addCleanup(patcher.stop)

    def native_manual_cycle(self,mode,target):
        self.native_rate_fixture(mode)
        self.m.activate_feature('native_rate_'+mode,2.);self.m.monitor_tick()
        self.assertTrue(self.m.health_active(),self.s.b.report());self.assertEqual(self.rate_calls,[])
        self.s.advance(dt=.2);self.assertEqual(self.rate_value,target);self.assertEqual(self.rate_calls,['add'])
        self.m.request_stop('test');self.s.advance(dt=.2);self.s.advance(dt=.2)
        self.assertEqual(self.rate_calls,['add','remove']);self.assertEqual(self.rate_value,2.)
        self.assertFalse(self.m.health_fault());self.assertFalse(self.m.health_active());self.assertEqual(self.s.calls,[])

    def test_native_rate_manual_cooldown_integration(self):self.native_manual_cycle('cooldown',4.)
    def test_native_rate_manual_duration_integration(self):self.native_manual_cycle('duration',1.)
    def test_native_rate_persistent_cooldown_integration(self):
        self.native_rate_fixture('cooldown')
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_native_rate_cooldown':True,'native_rate_selection_cooldown':2.})
        for _ in range(4):self.s.advance(dt=.3)
        self.assertIn('native_rate_cooldown',self.m._automation_leases,str(self.m._automation_status));self.assertEqual(self.rate_calls,['add']);self.assertEqual(self.rate_value,4.)
        self.m.restore_all_ui()
        for _ in range(4):self.s.advance(dt=.3)
        self.assertEqual(self.rate_calls,['add','remove']);self.assertEqual(self.rate_value,2.);self.assertEqual(self.s.calls,[])
    def test_native_rate_uses_no_refill_binding(self):
        self.s.funcs[:]=[f for f in self.s.funcs if f.Name!='RefillPercentage']
        self.native_manual_cycle('cooldown',4.)
    def test_native_rate_wrong_percent_no_add(self):
        self.native_rate_fixture('cooldown');self.override['GetCooldownAsPercentInternal']=.7
        self.m.activate_feature('native_rate_cooldown',2.);self.m.monitor_tick();self.s.advance(dt=.2)
        self.assertFalse(self.m.health_active());self.assertEqual(self.rate_calls,[])
        self.assertIn('native action skill percent disagrees',self.s.b.report())
    def test_native_rate_persistent_duration_live_edit(self):
        self.native_rate_fixture('duration')
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_native_rate_duration':True,'native_rate_selection_duration':2.})
        for _ in range(4):self.s.advance(dt=.3)
        self.assertEqual(self.rate_value,1.);self.assertEqual(self.rate_calls,['add'])
        self.m.apply({'native_rate_selection_duration':4.})
        for _ in range(6):self.s.advance(dt=.3)
        self.assertEqual(self.rate_value,.5);self.assertEqual(self.rate_calls,['add','remove','add'])
        self.m.restore_all_ui()
        for _ in range(4):self.s.advance(dt=.3)
        self.assertEqual(self.rate_value,2.);self.assertEqual(self.rate_calls,['add','remove','add','remove']);self.assertEqual(self.s.calls,[])
    def test_native_rate_charge_pool_still_excluded(self):
        self.native_rate_fixture('cooldown');self.s.d.ChargeComponentID=self.s.g
        self.m.activate_feature('native_rate_cooldown',2.);self.m.monitor_tick();self.s.advance(dt=.2)
        self.assertFalse(self.m.health_active());self.assertEqual(self.rate_calls,[]);self.assertEqual(self.s.calls,[])
    def test_native_rate_reader_cannot_arm_pulse(self):
        import importlib
        S=importlib.import_module(self.m.__package__+'.skill_pulse')
        f=self.s.b.f;u=f.sdk.unreal
        ref,api=S.bind(self.s.funcs,self.m.loot_bound,read_only=True)
        cross=S.bind_action_percent(self.s.funcs,self.m.loot_bound,'cooldown',ref)
        reader=S.SkillPulse(lambda:(f.pc,f.pawn,f.state,True),u.WeakPointer,u.FGameDataHandle,u.WrappedInlineStruct,u.WrappedStruct,ref,api,lambda:self.s.skills,lambda:self.s.now,lambda:1,lambda x:None,'cooldown',adaptive_api=cross,read_only=True)
        self.assertEqual(len(reader.api),3);self.assertEqual(reader.resolve(initial=True,refresh=True)[4],(.2,.8))
        with self.assertRaisesRegex(ValueError,'cannot arm'):reader.begin()
        reader.tick(True);self.assertIsNone(reader.record);self.assertEqual(self.s.calls,[])
