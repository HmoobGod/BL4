"""Synthetic native-shaped readiness and dispatch; no game execution."""
import unittest
from types import SimpleNamespace as N
from test_health_pulse_r17 import HealthPulse,FGameDataHandle
from test_combat_r13 import Node,attr,typ,desc,objdesc

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.h=HealthPulse();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.m=self.h.m;self.p=self.h.p;self.calls=[];self.now=100.;self.closed=True
        from bl4_custom_foundation.repair_assist import RepairAssist,bind,GET,USE,PAWN,KIT
        self.bind=bind;self.GET=GET;self.USE=USE;self.PAWN=PAWN;self.KIT=KIT
        self.p.Class._path_name=lambda:PAWN;self.p._path_name=lambda:'/Game/Test.Pawn'
        maximum=attr(2);maximum._type.Name='GbxAttributeInteger';maximum._type._properties=lambda:[type('ZIntProperty',(),{'Name':'Value','ArrayDim':1})()]
        self.minimum=attr(.1);hs=self.p.HealthState;old=hs._type._properties;hs._type._properties=lambda:old()+[desc('minhealthpercentmissingtoheal',self.minimum._type)];hs.minhealthpercentmissingtoheal=self.minimum
        self.kit=Node(Name='kit_instance',Class=typ('RepairKit',objdesc('OwningCharacter',PAWN),desc('MaxCharges',maximum._type),type('ZIntProperty',(),{'Name':'ActiveCharges','ArrayDim':1})(),type('ZBoolProperty',(),{'Name':'bIsUsing','ArrayDim':1})()),OwningCharacter=self.p,Owner=self.p,MaxCharges=maximum,ActiveCharges=2,bIsUsing=False,HasAuthority=lambda:True,IsActorBeingDestroyed=lambda:False)
        self.kit.Class._path_name=lambda:KIT;self.current=self.kit
        self.fn=Node(Name='StartUsingRepairKit',NumParams=0,Outer=Node(Name=PAWN),_properties=lambda:[],_path_name=lambda:USE)
        def use():self.calls.append('use');self.kit.ActiveCharges-=1
        use.func=self.fn;self.p.StartUsingRepairKit=use
        self.pc=self.h.b.f.pc;self.state=self.h.b.f.state;self.ok=True;self.tid=1;self.messages=[]
        self.context=lambda:(self.pc,self.p,self.state,self.ok)
        self.a=RepairAssist(self.context,lambda o:lambda:o,FGameDataHandle,lambda p:self.current,self.fn,lambda:self.now,lambda:self.tid,self.messages.append,lambda:self.closed)
        self.hp(.3)
    def hp(self,p):self.h.cur._values['Value']=p*100
    def tick(self,dt=.25):self.now+=dt;self.a.tick(True)
    def arm(self):self.assertTrue(self.a.begin())
    def cycle(self):self.tick();self.tick()
    def test_normal_one_shot(self):
        self.arm();self.tick();self.assertEqual(self.calls,[]);self.tick();self.assertEqual(self.calls,['use']);self.assertEqual(self.kit.ActiveCharges,1);self.cycle();self.assertEqual(self.calls,['use']);self.assertIsNone(self.a.record)
    def test_high_health(self):self.hp(.36);self.arm();self.cycle();self.assertEqual(self.calls,[])
    def test_threshold_edge(self):self.hp(.35);self.arm();self.cycle();self.assertEqual(self.calls,['use'])
    def test_no_charges(self):self.kit.ActiveCharges=0;self.arm();self.cycle();self.assertEqual(self.calls,[])
    def test_busy(self):self.kit.bIsUsing=True;self.arm();self.cycle();self.assertEqual(self.calls,[])
    def test_threshold_native(self):self.minimum._values['Value']=.9;self.arm();self.cycle();self.assertEqual(self.calls,[])
    def test_menu_open(self):self.closed=False;self.arm();self.cycle();self.assertEqual(self.calls,[]);self.closed=True;self.tick();self.assertEqual(self.calls,[]);self.tick();self.assertEqual(self.calls,['use'])
    def test_health_recovers_between_samples(self):self.arm();self.tick();self.hp(.5);self.tick();self.hp(.3);self.tick();self.assertEqual(self.calls,[])
    def test_expiry(self):self.arm();self.tick(30);self.assertIsNone(self.a.record);self.assertEqual(self.calls,[])
    def test_join(self):self.arm();self.tick();self.ok=False;self.tick();self.assertEqual(self.calls,[]);self.assertIsNone(self.a.record)
    def test_wrong_thread(self):self.arm();self.tid=2;self.cycle();self.assertEqual(self.calls,[])
    def test_owner(self):self.kit.OwningCharacter=Node();self.assertFalse(self.a.begin())
    def test_destroyed(self):self.kit.IsActorBeingDestroyed=lambda:True;self.assertFalse(self.a.begin())
    def test_replacement(self):self.arm();self.current=Node();self.cycle();self.assertEqual(self.calls,[]);self.assertIsNone(self.a.record)
    def test_injured(self):self.p.HealthCondition=N(name='Injured');self.assertFalse(self.a.begin())
    def test_bad_count(self):self.kit.ActiveCharges=True;self.assertFalse(self.a.begin())
    def test_changed_binding(self):self.arm();self.p.StartUsingRepairKit=lambda:None;self.cycle();self.assertEqual(self.calls,[])
    def test_stop(self):self.arm();self.tick();self.a.stop('manual');self.tick();self.assertEqual(self.calls,[])
    def test_uncertain_request(self):
        def bad():self.calls.append('uncertain');raise RuntimeError('native failed')
        bad.func=self.fn;self.p.StartUsingRepairKit=bad;self.arm();self.cycle();self.assertTrue(self.a.fault);self.assertFalse(self.a.begin());self.assertEqual(self.calls,['uncertain'])
    def test_rejected_native_request_no_retry(self):
        def ignored():self.calls.append('ignored')
        ignored.func=self.fn;self.p.StartUsingRepairKit=ignored;self.arm();self.cycle();self.cycle();self.assertEqual(self.calls,['ignored'])
    def test_reentrant_stop(self):
        self.arm();self.tick();self.a.getter=lambda p:(self.a.stop('reentrant'),self.kit)[1];self.tick();self.assertEqual(self.calls,[])
    def test_session_loss_during_final_read(self):
        self.arm();self.tick();n=[0]
        def get(p):
            n[0]+=1
            if n[0]==2:self.ok=False
            return self.kit
        self.a.getter=get;self.tick();self.assertEqual(self.calls,[])
    def test_exact_binding(self):
        p=[objdesc('User','/Script/Engine.Actor'),objdesc('ReturnValue',self.KIT)]
        f=Node(_path_name=lambda:self.GET,_properties=lambda:p)
        self.assertEqual(self.bind([f,self.fn],lambda *a:'getter'),('getter',self.fn))
        self.fn.NumParams=1
        with self.assertRaises(ValueError):self.bind([f,self.fn],lambda *a:'getter')
    def test_f8_integration(self):
        p=[objdesc('User','/Script/Engine.Actor'),objdesc('ReturnValue',self.KIT)]
        cdo=Node();f=Node(Name='GetRepairKit',_path_name=lambda:self.GET,_properties=lambda:p,NumParams=2,Outer=Node(ClassDefaultObject=cdo))
        def getter(p):return self.kit
        getter.func=f;cdo.GetRepairKit=getter
        sdk=self.h.b.f.sdk;old=sdk.find_all;sdk.find_all=lambda *a,**k:list(old(*a,**k))+[f,self.fn] if a[0]=='Function' else old(*a,**k)
        self.m.activate_feature('repair_assist',1.);self.m.monitor_tick();self.assertTrue(self.m.health_active());self.m.close_menu();self.h.now+=.25;self.m.monitor_tick();self.h.now+=.25;self.m.monitor_tick();self.assertEqual(self.calls,['use'])

class RepairContinuousTests(unittest.TestCase):
    def setUp(self):
        self.t=RepairTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
        self.a=self.t.a;self.a.continuous=True;self.k=self.t.kit;self.calls=self.t.calls
    def tick(self,n=1):
        for _ in range(n):self.t.tick()
    def arm(self):self.t.arm();self.tick(2);self.assertEqual(len(self.calls),1)
    def complete(self):
        self.k.bIsUsing=True;self.tick();self.k.bIsUsing=False;self.tick()
        self.k.ActiveCharges+=1;self.t.hp(.6);self.tick(2)
    def next_use(self):self.t.hp(.3);self.tick(2)
    def test_three_distinct_cycles_and_cap(self):
        self.arm();self.complete();self.next_use();self.assertEqual(len(self.calls),2)
        self.complete();self.next_use();self.assertEqual(len(self.calls),3);self.assertIsNone(self.a.record);self.tick(5);self.assertEqual(len(self.calls),3)
    def test_no_busy_witness(self):
        self.arm();self.t.hp(.6);self.tick(2);self.k.ActiveCharges=2;self.tick(3);self.next_use();self.assertEqual(len(self.calls),1)
    def test_no_charge_restoration(self):
        self.arm();self.k.bIsUsing=True;self.tick();self.k.bIsUsing=False;self.t.hp(.6);self.tick(4);self.next_use();self.assertEqual(len(self.calls),1)
    def test_health_hysteresis(self):
        self.arm();self.k.bIsUsing=True;self.tick();self.k.bIsUsing=False;self.tick();self.k.ActiveCharges=2;self.t.hp(.49);self.tick(2);self.next_use();self.assertEqual(len(self.calls),1)
    def test_one_high_sample_not_enough(self):
        self.arm();self.k.bIsUsing=True;self.tick();self.k.bIsUsing=False;self.tick();self.k.ActiveCharges=2;self.t.hp(.6);self.tick();self.next_use();self.assertEqual(len(self.calls),1)
    def test_no_recovery_if_menu_open(self):
        self.arm();self.t.closed=False;self.complete();self.t.closed=True;self.next_use();self.assertEqual(len(self.calls),1)
    def test_timeout_no_retry(self):
        self.arm();self.t.tick(60);self.assertIsNone(self.a.record);self.next_use();self.assertEqual(len(self.calls),1)
    def test_join_during_witness(self):
        self.arm();self.t.ok=False;self.tick();self.assertIsNone(self.a.record);self.assertEqual(len(self.calls),1)
    def test_manual_stop_during_witness(self):
        self.arm();self.a.stop('owner');self.complete();self.next_use();self.assertEqual(len(self.calls),1)
    def test_extra_consumption(self):
        self.arm();self.k.ActiveCharges=0;self.tick();self.assertIsNone(self.a.record)
    def test_recharge_before_idle(self):
        self.arm();self.k.bIsUsing=True;self.tick();self.k.ActiveCharges=2;self.tick();self.assertIsNone(self.a.record)
    def test_second_use_during_recharge(self):
        self.arm();self.k.bIsUsing=True;self.tick();self.k.bIsUsing=False;self.tick();self.k.bIsUsing=True;self.tick();self.assertIsNone(self.a.record)
    def test_maximum_changes(self):
        self.arm();self.k.MaxCharges._values['Value']=3;self.tick();self.assertIsNone(self.a.record)
    def test_manual_use_after_rearm(self):
        self.arm();self.complete();self.k.ActiveCharges=1;self.next_use();self.assertIsNone(self.a.record);self.assertEqual(len(self.calls),1)
    def test_replacement_after_request(self):
        self.arm();self.t.current=Node();self.tick();self.assertIsNone(self.a.record)
    def test_rejected_native_request(self):
        def ignored():self.calls.append('ignored')
        ignored.func=self.t.fn;self.t.p.StartUsingRepairKit=ignored;self.arm();self.t.tick(60);self.assertIsNone(self.a.record);self.assertEqual(len(self.calls),1)
    def test_fault_after_dispatch(self):
        def bad():self.calls.append('bad');raise RuntimeError('native failure')
        bad.func=self.t.fn;self.t.p.StartUsingRepairKit=bad;self.arm();self.assertTrue(self.a.fault);self.assertIsNone(self.a.record)
    def test_f8_session_integration(self):
        t=self.t;p=[objdesc('User','/Script/Engine.Actor'),objdesc('ReturnValue',t.KIT)]
        cdo=Node();f=Node(Name='GetRepairKit',_path_name=lambda:t.GET,_properties=lambda:p,NumParams=2,Outer=Node(ClassDefaultObject=cdo))
        def getter(p):return t.kit
        getter.func=f;cdo.GetRepairKit=getter
        sdk=t.h.b.f.sdk;old=sdk.find_all;sdk.find_all=lambda *a,**k:list(old(*a,**k))+[f,t.fn] if a[0]=='Function' else old(*a,**k)
        t.m.activate_feature('repair_assist_continuous',1.);t.m.monitor_tick();self.assertTrue(t.m.health_active());t.m.close_menu()
        for _ in range(2):t.h.now+=.25;t.m.monitor_tick()
        self.assertEqual(len(self.calls),1);self.assertTrue(t.m.health_active());self.assertTrue(t.m._health_pulse.continuous)
        t.m.request_stop('test',immediate=True);self.assertFalse(t.m.health_active())

class RepairPersistentTests(unittest.TestCase):
    def setUp(self):
        self.t=RepairTests();self.t.setUp();self.addCleanup(self.t.doCleanups)
        t=self.t;self.m=t.m
        p=[objdesc('User','/Script/Engine.Actor'),objdesc('ReturnValue',t.KIT)]
        cdo=Node();f=Node(Name='GetRepairKit',_path_name=lambda:t.GET,_properties=lambda:p,NumParams=2,Outer=Node(ClassDefaultObject=cdo))
        def getter(p):return t.current
        getter.func=f;cdo.GetRepairKit=getter
        sdk=t.h.b.f.sdk;old=sdk.find_all;sdk.find_all=lambda *a,**k:list(old(*a,**k))+[f,t.fn] if a[0]=='Function' else old(*a,**k)
        self.m.close_menu()
    def advance(self,n=1):
        for _ in range(n):self.t.h.now+=.3;self.m.monitor_tick()
    def arm(self,**extra):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_automation_repair':True,**extra});self.advance(4)
    def test_default_off(self):
        self.assertFalse(self.m.AUTOMATION_OPTIONS['repair'].value)
        self.m.apply({'persistent_master':True,'persistent_offline':True});self.advance(4);self.assertEqual(self.t.calls,[])
    def test_actual_adapter_with_rarity(self):
        self.arm(persistent_legendary_weight=True,legendary_weight=2.)
        self.assertIn('legendary_weight',self.m._controller.records)
        self.assertEqual(self.t.calls,['use']);self.assertTrue(self.m._automation_leases['repair'].continuous)
        self.assertIsNone(self.m._health_pulse)
    def test_disable_keeps_rarity(self):
        self.arm(persistent_legendary_weight=True,legendary_weight=2.)
        self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['repair'],False);self.advance(4)
        self.assertNotIn('repair',self.m._automation_leases);self.assertIn('legendary_weight',self.m._controller.records);self.assertEqual(self.t.calls,['use'])
    def test_join_no_request(self):
        self.t.hp(.8);self.arm();self.t.hp(.3);self.advance();self.t.h.b.f.players=2;self.advance(3)
        self.assertEqual(self.t.calls,[]);self.assertNotIn('repair',self.m._automation_leases)
    def test_no_implicit_restart(self):
        self.arm();lease=self.m._automation_leases['repair'];lease.stop('test');self.advance(4)
        self.assertNotIn('repair',self.m._automation_leases);self.assertEqual(self.t.calls,['use'])
    def test_restore_all(self):
        self.t.hp(.8);self.arm();self.m.request_stop('owner');self.t.hp(.3);self.advance(4)
        self.assertNotIn('repair',self.m._automation_leases);self.assertEqual(self.t.calls,[])
