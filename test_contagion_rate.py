"""Exact Contagion main native rate; synthetic SDK calls, not game certification."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace as N
from test_requested_named_cooldown import NamedCooldown
from test_native_resource_rates import NativeRateTests
from test_skill_pulse_r19 import Handle

class ContagionRateTests(unittest.TestCase):
    def setUp(self):
        self.n=NamedCooldown();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.s,self.m=self.n.s,self.n.m
        import importlib
        R=importlib.import_module(self.m.__package__+".native_resource_rates")
        S=importlib.import_module(self.m.__package__+".skill_pulse")
        self.R,self.S=R,S
        self.s.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter'
        self.s.p._path_name=lambda:'/Game/Test.LocalPawn'
        self.s.b.f.sdk.unreal.FGbxDefPtr=object
        self.s.h[0]._name=R.CONTAGION_RESOURCE
        self.n.aux._name=R.CONTAGION_AUX
        self.n.values={R.CONTAGION_AUX:.4}
        self.defn=N(Context=N(ResourceDef=self.s.h[0]));self.rate=2.;self.peer=3.;self.events=[];self.handle=object()
        def definition(m):
            self.assertEqual(m,R.CONTAGION_MODE);return self.defn,('exact contagion definition',)
        def read(m,pawn):
            self.assertEqual(m,R.CONTAGION_MODE);self.assertIs(pawn,self.s.p);return self.rate
        def peer(name,pawn,default):
            self.assertEqual(name,R.CONTAGION_PEER);self.assertIs(pawn,self.s.p);return self.peer
        def add(m,d,pawn,selection):
            self.assertEqual(m,R.CONTAGION_MODE);self.assertIs(d,self.defn);self.assertIs(pawn,self.s.p)
            self.events.append('add');self.rate*=R.trial_amount(m,selection);return self.handle,True
        def remove(h):
            self.assertIs(h,self.handle);self.events.append('remove');self.rate=2.
        self.fake=N(definition=definition,read=read,add=add,remove=remove,calls={'GetValueOfAttribute':peer})
        self.patcher=patch.object(R,'NativeBinding',return_value=self.fake);self.patcher.start();self.addCleanup(self.patcher.stop)
    def arm(self):
        self.m.activate_feature('native_rate_cooldown',2.);self.m.monitor_tick();self.s.advance(dt=.2)
    def finish(self):
        self.m.request_stop('test');self.s.advance(dt=.3);self.s.advance(dt=.3)
    def no_mutation(self):
        self.assertEqual(self.events+self.n.direct+self.s.calls+self.n.n.calls,[])
    def test_manual_main_only_and_restore(self):
        self.arm();self.assertEqual(self.events,['add'],self.s.b.report());self.assertEqual(self.rate,4.);self.assertEqual(self.peer,3.)
        self.finish();self.assertEqual(self.events,['add','remove']);self.assertEqual(self.rate,2.);self.assertFalse(self.m.health_fault());self.assertEqual(self.n.direct+self.s.calls+self.n.n.calls,[])
    def test_persistent_main_rate_and_saved_edit(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_native_rate_cooldown':True,'native_rate_selection_cooldown':2.})
        for _ in range(4):self.s.advance(dt=.3)
        self.assertEqual(self.events,['add'],str(self.m._automation_status));self.assertEqual(self.rate,4.)
        self.m.apply({'native_rate_selection_cooldown':3.})
        for _ in range(6):self.s.advance(dt=.3)
        self.assertEqual(self.events,['add','remove','add']);self.assertEqual(self.rate,6.)
        self.m.restore_all_ui()
        for _ in range(4):self.s.advance(dt=.3)
        self.assertEqual(self.events,['add','remove','add','remove']);self.assertEqual(self.rate,2.)
        self.assertEqual(self.n.direct+self.s.calls+self.n.n.calls,[])
    def test_no_refill_or_adjust_writer_required(self):
        self.s.funcs[:]=[f for f in self.s.funcs if f.Name not in ('RefillPercentage','AdjustResourcePoolValue','RefillCooldownInternal','RefillDurationInternal')]
        self.arm();self.assertEqual(self.events,['add'],self.s.b.report());self.finish();self.assertEqual(self.events,['add','remove'])
    def test_wrong_native_resource(self):
        self.defn.Context.ResourceDef=Handle(self.R.CONTAGION_RESOURCE);self.arm();self.no_mutation()
    def test_unknown_auxiliary(self):
        self.n.aux._name='different_aux';self.n.values={'different_aux':.4};self.arm();self.no_mutation()
    def test_charge_layout_refused(self):
        self.n.add_charge();self.n.values[self.n.ch._name]=.5;self.arm();self.no_mutation()
    def test_peer_rate_unavailable(self):
        self.peer=-123456.;self.arm();self.no_mutation()
    def test_peer_rate_drift_restores_original(self):
        self.arm();self.assertEqual(self.events,['add']);self.peer=5.;self.s.advance(dt=.3);self.s.advance(dt=.3)
        self.assertEqual(self.events,['add','remove']);self.assertEqual(self.rate,2.);self.assertEqual(self.peer,5.);self.assertTrue(self.m.health_fault())
    def test_named_reader_no_writer(self):
        api=self.S.bind_direct_cooldown(self.s.funcs,self.m.loot_bound,read_only=True)
        self.assertIsNone(api[2]);self.assertEqual(api[3],1)
    def test_direct_main_mismatch(self):
        self.n.read_effect=lambda name,h:None
        f=self.n.funcs[0];old=f.Outer.ClassDefaultObject.GetResourcePoolValue
        def read(p,h):return old(p,h)+10.
        read.func=f;f.Outer.ClassDefaultObject.GetResourcePoolValue=read
        self.arm();self.no_mutation()
    def test_named_native_binding_metadata(self):
        self.patcher.stop()
        t=NativeRateTests();t.setUp();self.addCleanup(t.doCleanups)
        mode=t.R.CONTAGION_MODE;d,key=t.binding.definition(mode)
        self.assertEqual(d.Context.ResourceDef._name,t.R.CONTAGION_RESOURCE)
        self.assertEqual(d.Value.Property.PropertyPath,'ActiveRegenerationRate')
        self.assertEqual(t.R.trial_amount(mode,3.),3.)
        t.cycle(mode,2.,4.)
