"""Synthetic F8 and native-call admission, not native game evidence."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Combat, Node, attr, typ, desc, arraydesc

class FGameDataHandle(Node):
    def __init__(self,name,color,variation):
        super().__init__(_name=name,_type_handle=1,DisplayColor=N(name=color),Variation=N(name=variation))

class HealthPulse(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.m=self.c.m; self.p=self.c.p; self.b=self.c.b; self.calls=[]; self.now=100.; self.pct=.5
        self.m.time=N(monotonic=lambda:self.now)
        from bl4_custom_foundation.health_pulse import Pulse, SPECS, PATH, bind
        self.Pulse=Pulse; self.SPECS=SPECS;self.PATH=PATH; self.bind=bind
        self.hp=FGameDataHandle('HealthType_FleshMock','FleshRed','IsGeneric')
        self.sh=FGameDataHandle('HealthType_ShieldMock','EnergyBlue','IsShield')
        self.cur=attr(50.); self.max=attr(100.); self.disabled=attr(0); self.disabled._type.Name='GbxAttributeInteger'
        handle_desc=type('ZGameDataHandleProperty',(),{'Name':'HealthType','ArrayDim':1})()
        self.layer_type=typ('HealthTypeState',handle_desc,desc('SimpleCurrentHealth',self.cur._type),desc('SimpleMaxHealth',self.max._type))
        # Use same exact reflected type descriptors for both layers.
        self.flesh=Node(_type=self.layer_type,HealthType=self.hp,SimpleCurrentHealth=self.cur,SimpleMaxHealth=self.max)
        self.shield=Node(_type=self.layer_type,HealthType=self.sh)
        h=self.p.HealthState;h.owner=self.p;h.bCurrentlyDead=False;h.HealingDisabled=self.disabled;h.HealthTypeStates=[self.shield,self.flesh]
        h._type=typ('OakCharacterHealthState',desc('HealingDisabled',self.disabled._type),arraydesc('HealthTypeStates',desc('inner',self.layer_type)))
        condition=type('ZEnumProperty',(),{'Name':'HealthCondition','ArrayDim':1,'Enum':N(_path_name=lambda:'/Script/OakGame.ECharacterHealthCondition')})()
        self.p.Class._properties=lambda:[desc('HealthState',h._type),condition];self.p.HealthCondition=N(name='Healthy')
        self.b.f.sdk.unreal.FGameDataHandle=FGameDataHandle
        self.api=(self.layer,self.percent,self.refill)
        self.funcs=[]
        for (name,sig),call in zip(SPECS.items(),self.api,strict=True):
            path=PATH+name
            props=[type(k,(),{'Name':n,'ArrayDim':1})() for n,k in sig]
            props[0].PropertyClass=N(_path_name=lambda:'/Script/Engine.Actor')
            cdo=N();owner=N(_path_name=lambda:PATH[:-1],ClassDefaultObject=cdo)
            f=N(Name=name,Outer=owner,NumParams=len(props),_path_name=lambda path=path:path,_properties=lambda props=props:props)
            def bound(*a,call=call):return call(*a)
            bound.func=f;setattr(cdo,name,bound);self.funcs.append(f)
        old=self.b.f.sdk.find_all
        self.b.f.sdk.find_all=lambda *a,**k:list(old(*a,**k))+self.funcs if a[0]=='Function' else old(*a,**k)
    def layer(self,p,h,top):
        self.assertIs(p,self.p); self.assertIs(h,self.hp); self.assertIs(top,False);return 1
    def percent(self,p,layer):self.assertEqual(layer,1);return self.pct
    def refill(self,p,h,amount,cap):
        self.assertIs(p,self.p); self.assertIs(h,self.hp);self.assertEqual(cap,1.0)
        self.calls.append(amount);self.pct=min(1.,self.pct+amount);self.cur._values['Value']=self.pct*100.
    def start(self):self.m.activate_feature('health_pulse',1.);self.m.monitor_tick()
    def advance(self,dt=1.):self.now+=dt;self.m.monitor_tick()
    def test_native_pulse_and_stop(self):
        self.start();self.assertTrue(self.m.health_active());self.assertEqual(self.calls,[])
        self.advance();self.advance();self.assertEqual(self.calls,[.01,.01]);self.m.request_stop('restore');self.advance();self.assertEqual(len(self.calls),2);self.assertFalse(self.m.health_active())
    def test_no_catchup(self):self.start();self.advance(10);self.assertEqual(len(self.calls),1);self.advance(20);self.assertFalse(self.m.health_active());self.assertEqual(len(self.calls),1)
    def test_join(self):self.start();self.b.f.players=2;self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_injured(self):self.p.HealthCondition=N(name='Injured');self.start();self.assertFalse(self.m.health_active());self.assertEqual(self.calls,[])
    def test_healing_disabled(self):self.disabled._values['Value']=1;self.start();self.assertFalse(self.m.health_active())
    def test_shield_only(self):self.p.HealthState.HealthTypeStates=[self.shield];self.start();self.assertFalse(self.m.health_active())
    def test_duplicate_flesh(self):self.p.HealthState.HealthTypeStates.append(self.flesh);self.start();self.assertFalse(self.m.health_active())
    def test_unresolved_percent(self):self.pct=50.;self.start();self.assertFalse(self.m.health_active())
    def test_ratio_mismatch(self):self.pct=.2;self.start();self.assertFalse(self.m.health_active())
    def test_missing_binding(self):self.funcs.pop();self.start();self.assertFalse(self.m.health_active())
    def test_pool_changed(self):self.start();self.hp._name='HealthType_Replacement';self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_fault_latch(self):
        self.start();self.m._health_pulse.api=(self.layer,self.percent,lambda *a: (_ for _ in ()).throw(RuntimeError('uncertain')))
        self.advance();self.assertTrue(self.m.health_fault());self.start();self.assertFalse(self.m.health_active())
        self.m.activate_feature('jump',2.);self.advance();self.assertIsNone(self.m._controller)
    def test_no_effect_stop(self):
        self.start();self.m._health_pulse.api=(self.layer,self.percent,lambda *a:self.calls.append(a[2]));self.advance();self.advance();self.assertEqual(self.calls,[.01]);self.assertFalse(self.m.health_active())
    def test_full_no_heal(self):self.pct=1.;self.cur._values['Value']=100.;self.start();self.advance();self.assertEqual(self.calls,[]);self.assertTrue(self.m.health_active())
    def test_consent_withdraw(self):self.start();self.m._offline_confirmed=False;self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_disabled(self):self.start();self.m.disabled();self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_reset(self):self.start();self.m.reset();self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_master_switch(self):self.start();self.m.set_auto_setting(self.m.auto_master,True);self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_other_feature_exclusion(self):self.c.activate('jump',1.5);self.start();self.assertFalse(self.m.health_active());self.assertEqual(self.calls,[])
    def test_f8_queue(self):
        self.m._category=6;self.b.gui.imgui.clicks={'Start experimental health recovery (30 sec)'};self.m.draw();self.assertFalse(self.m.health_active());self.assertEqual(self.calls,[]);self.m.monitor_tick();self.assertTrue(self.m.health_active());self.advance();self.assertEqual(self.calls,[.01])
    def test_context_changes_during_read(self):
        self.start()
        def read(p,layer):
            self.b.f.players=2
            return self.pct
        self.m._health_pulse.api=(self.layer,read,self.refill)
        self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_original_pawn_changed(self):
        self.start();self.b.f.pc.Pawn=Node();self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_no_heal_after_stop_inside_read(self):
        self.start()
        def read(p,layer):
            self.m.request_stop('reentrant stop')
            return self.pct
        self.m._health_pulse.api=(self.layer,read,self.refill)
        self.advance();self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
