"""Synthetic direct primary cooldown for charge/aux layouts, not game certification."""
import unittest
from types import SimpleNamespace as N
from test_native_skill_r58 import NativeSkill
from test_skill_pulse_r19 import Handle, Inline
from test_combat_r13 import Node,typ

class NamedCooldown(unittest.TestCase):
    def setUp(self):
        self.n=NativeSkill();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.s=self.n.s;self.m=self.n.m;self.direct=[];self.funcs=[];self.values={};self.effect=None;self.read_effect=None
        self.s.h[0]._name='Resource_DarkSiren_ActionSkill_PhaseShard_Cooldown'
        for d in self.s.defs:d._type_handle=2
        self.aux=Handle('distinct_aux');self.auxdef=Handle('distinct_aux_def',resource=self.aux);self.auxdef._type_handle=2
        self.s.d.AuxCooldownPoolDefs=[self.auxdef];self.values[self.aux._name]=.4
        self.ch=Handle('distinct_charge');self.values[self.ch._name]=.5
        self.cg=Node(_type=self.s.gt,A=5,B=2,C=3,D=4)
        self.charge=Inline(_type=typ('/Script/OakGame.GbxSkillComponentData_Charges',parents=(typ('/Script/GbxGame.GbxSkillComponentData'),)),ComponentID=self.cg,ChargePoolHandle=self.ch)
        from bl4_custom_foundation.skill_pulse import DIRECT,DIRECT_NAMES,DIRECT_INTERFACE
        for name in DIRECT_NAMES:
            path=DIRECT+name
            props=[type(k,(),{'Name':n,'ArrayDim':1})() for n,k in (('owner','ZInterfaceProperty'),('InResource','ZGameDataHandleProperty'),('InValue' if name==DIRECT_NAMES[-1] else 'ReturnValue','ZFloatProperty'))]
            props[0].InterfaceClass=N(_path_name=lambda:DIRECT_INTERFACE);props[1].TypeHandle=1
            cdo=N();owner=N(_path_name=lambda:DIRECT[:-1],ClassDefaultObject=cdo)
            fn=N(Name=name,Outer=owner,NumParams=3,_path_name=lambda path=path:path,_properties=lambda props=props:props)
            def bound(pawn,h,*args,name=name):
                self.assertIs(pawn,self.s.p)
                if name==DIRECT_NAMES[-1]:
                    self.assertIs(h,self.s.h[0]);self.direct.append(args[0])
                    if self.effect:self.effect(args[0])
                    else:self.s.val[0]+=args[0]/100.
                    return
                if self.read_effect:self.read_effect(name,h)
                value=self.s.val[0] if h is self.s.h[0] else self.values[h._name]
                return value*100. if name==DIRECT_NAMES[0] else value
            bound.func=fn;setattr(cdo,name,bound);self.s.funcs.append(fn);self.funcs.append(fn)
    def add_charge(self):
        self.s.d.ChargeComponentID=self.cg;self.s.cls.SkillComponents.append(N(ComponentData=self.charge))
    def arm(self,rate=2.,**kw):self.n.arm(rate=rate,**kw)
    def trend(self):self.s.advance(.21);self.s.advance(.22)
    def stopped(self):self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def no_calls(self):self.assertEqual(self.direct+self.s.calls+self.n.calls,[])
    def test_auxiliary_primary_only(self):
        self.arm();self.trend();self.assertEqual(len(self.direct),1);self.assertAlmostEqual(self.direct[0],1.);self.assertAlmostEqual(self.s.val[0],.23);self.assertEqual(self.values[self.aux._name],.4);self.assertEqual(self.s.calls+self.n.calls,[])
    def test_charge_primary_only(self):
        self.s.d.AuxCooldownPoolDefs=[];self.add_charge();self.arm();self.trend();self.assertEqual(len(self.direct),1);self.assertEqual(self.values[self.ch._name],.5)
    def test_charge_and_auxiliary(self):
        self.add_charge();self.arm(rate=1.5);self.trend();self.assertAlmostEqual(self.direct[0],.5);self.assertEqual(self.values,{self.aux._name:.4,self.ch._name:.5})
    def test_ordinary_uses_original_dedicated(self):
        self.s.d.AuxCooldownPoolDefs=[];self.arm();self.trend();self.assertEqual(self.direct,[]);self.assertEqual(len(self.n.calls),1)
    def test_legacy_adaptive_stays_held(self):
        self.n.a.arm();self.trend();self.no_calls();self.stopped()
    def test_follow_stays_held(self):
        self.arm(follow_skill_cooldown=True);self.trend();self.no_calls();self.stopped()
    def test_missing_direct_stays_held(self):
        self.s.funcs.remove(self.funcs[-1]);self.arm();self.trend();self.no_calls();self.stopped()
    def test_wrong_interface(self):
        self.funcs[0]._properties()[0].InterfaceClass=N(_path_name=lambda:'wrong');self.arm();self.trend();self.no_calls();self.stopped()
    def test_wrong_handle_type(self):
        self.funcs[-1]._properties()[1].TypeHandle=9;self.arm();self.trend();self.no_calls();self.stopped()
    def test_unknown_name(self):
        self.s.h[0]._name='unrecognized_cooldown';self.arm();self.trend();self.no_calls();self.stopped()
    def test_aux_alias(self):
        self.auxdef.resource=self.s.h[0];self.arm();self.trend();self.no_calls();self.stopped()
    def test_casefold_alias(self):
        self.aux._name=self.s.h[0]._name.lower();self.arm();self.trend();self.no_calls();self.stopped()
    def test_charge_guid_invalid(self):
        self.s.d.ChargeComponentID=self.s.g;self.arm();self.trend();self.no_calls();self.stopped()
    def test_charge_alias(self):
        self.add_charge();self.charge.ChargePoolHandle=self.s.h[0];self.arm();self.trend();self.no_calls();self.stopped()
    def test_join(self):
        self.arm();self.s.advance(.21);self.s.b.f.players=2;self.s.advance(.22);self.no_calls();self.stopped()
    def test_stop_during_direct_read(self):
        self.arm();self.s.advance(.21);self.read_effect=lambda *_:self.m.request_stop('reentrant');self.s.advance(.22);self.no_calls()
    def test_late_peer_replacement(self):
        self.arm();self.s.advance(.21)
        def replace(name,h):
            if h is self.aux:self.auxdef.resource=Handle('replacement')
        self.read_effect=replace;self.s.advance(.22);self.no_calls();self.stopped()
    def test_large_refund_no_multiplier(self):
        self.arm();self.s.advance(.4);self.s.advance(.6);self.no_calls();self.s.advance(.61);self.s.advance(.62);self.assertEqual(len(self.direct),1)
    def test_peer_drift_fault(self):
        def effect(a):self.s.val[0]+=a/100.;self.values[self.aux._name]=.6
        self.effect=effect;self.arm();self.trend();self.assertTrue(self.m.automation_fault());self.assertEqual(len(self.direct),1)
    def test_overshoot_fault(self):
        self.effect=lambda a:self.s.val.__setitem__(0,.8);self.arm();self.trend();self.assertTrue(self.m.automation_fault())
    def test_ineffective_no_retry(self):
        self.effect=lambda a:None;self.arm();self.trend();self.s.advance(.23);self.s.advance(.24);self.assertEqual(len(self.direct),1);self.stopped()
    def test_one_x(self):
        self.arm(rate=1.);self.trend();self.no_calls()
    def test_duration_stays_held(self):
        self.n.arm('duration');self.s.advance(d=.79);self.s.advance(d=.78);self.no_calls();self.assertNotIn('skill_duration',self.m._automation_leases)
    def test_direct_readback_mismatch(self):
        self.arm();self.s.advance(.21);lease=self.m._automation_leases['skill_cooldown'];old=lease.direct_api[0]
        lease.direct_api=(lambda p,h:old(p,h)+10.,*lease.direct_api[1:]);self.s.advance(.22);self.no_calls();self.stopped()
    def test_charge_definition_handle(self):
        self.add_charge();d=Handle('charge_def',resource=self.ch);d._type_handle=2;self.charge.ChargePoolHandle=d;self.arm();self.trend();self.assertEqual(len(self.direct),1);self.assertEqual(self.values[self.ch._name],.5)
    def test_maximum_change_refuses(self):
        self.arm();self.s.advance(.21);lease=self.m._automation_leases['skill_cooldown'];a=lease.api;lease.api=(a[0],lambda r,h:a[1](r,h)*2.,lambda r,h:a[2](r,h)*2.,a[3]);self.s.advance(.22);self.no_calls();self.stopped()
    def test_reentrant_after_direct_dispatch_fault(self):
        self.effect=lambda a:self.m.request_stop('reentrant');self.arm();self.trend();self.assertEqual(len(self.direct),1);self.assertTrue(self.m.automation_fault())
    def test_live_rate_changes_reset_natural_trend(self):
        self.arm();self.s.advance(.21);self.m.apply({'adaptive_rate_skill_cooldown':1.5});self.s.advance(.22);self.s.advance(.23);self.no_calls();self.s.advance(.24);self.assertAlmostEqual(self.direct[0],.5)
