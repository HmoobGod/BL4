"""Dedicated native action skill refill: synthetic only, not native certification."""
import unittest
from types import SimpleNamespace as N
from test_adaptive_skill_r43 import AdaptiveSkill

class NativeSkill(unittest.TestCase):
    def setUp(self):
        self.a=AdaptiveSkill();self.a.setUp();self.addCleanup(self.a.doCleanups)
        self.s=self.a.s;self.m=self.a.m;self.calls=[];self.refills=[];self.effect=None
        from bl4_custom_foundation.skill_pulse import ACTION, REFILL_ENUM
        for idx,mode in enumerate(('Cooldown','Duration')):
            name='Refill'+mode+'Internal';path=ACTION+name
            props=[type(k,(),{'Name':n,'ArrayDim':1})() for n,k in (('ComponentReference','ZStructProperty'),('Percent','ZFloatProperty'),('RefillMode','ZEnumProperty'))]
            props[0].Struct=self.s.rt;props[2].Enum=N(_path_name=lambda:REFILL_ENUM)
            cdo=N();owner=N(_path_name=lambda:ACTION[:-1],ClassDefaultObject=cdo)
            f=N(Name=name,Outer=owner,NumParams=3,_path_name=lambda path=path:path,_properties=lambda props=props:props)
            def bound(r,amount,mode,idx=idx):
                self.assertIs(r.Context,self.s.script);self.assertIs(r.ComponentID,self.s.g);self.assertEqual(mode,0)
                self.calls.append((idx,amount,mode))
                if self.effect:self.effect(idx,amount)
                else:self.s.val[idx]+=amount
            bound.func=f;setattr(cdo,name,bound);self.s.funcs.append(f);self.refills.append(f)
    def arm(self,mode='cooldown',rate=2.,**kwargs):
        self.a.arm(mode,rate,**{'native_refill_skill_'+mode:True},**kwargs)
    def trend(self,mode='cooldown'):
        if mode=='cooldown':self.s.advance(.3);self.s.advance(.4)
        else:self.s.advance(d=.7);self.s.advance(d=.6)
    def test_default_off(self):self.assertTrue(all(o.value is False for o in self.m.SKILL_NATIVE.values()))
    def test_cooldown_dedicated_only(self):
        self.arm();self.trend();self.assertEqual(self.s.calls,[]);self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][0],0);self.assertAlmostEqual(self.calls[0][1],.01)
    def test_duration_dedicated_only(self):
        self.arm('duration');self.trend('duration');self.assertEqual(self.s.calls,[]);self.assertEqual(self.calls[0][0],1)
    def test_fractional_rate(self):
        self.arm(rate=1.5);self.s.advance(.21);self.s.advance(.22);self.assertAlmostEqual(self.calls[0][1],.005)
    def test_one_x(self):self.arm(rate=1.);self.trend();self.assertEqual(self.calls,[])
    def test_missing_no_fallback(self):
        self.s.funcs.remove(self.refills[0]);self.arm();self.trend();self.assertEqual(self.calls+self.s.calls,[]);self.assertNotIn('skill_cooldown',self.m._automation_leases)
    def test_wrong_enum(self):
        self.refills[0]._properties()[2].Enum=N(_path_name=lambda:'wrong');self.arm();self.trend();self.assertEqual(self.calls+self.s.calls,[])
    def test_non_adaptive_hold(self):
        self.a.t.arm('cooldown',native_refill_skill_cooldown=True);self.trend();self.assertEqual(self.calls+self.s.calls,[])
    def test_mode_change_no_fallback(self):
        self.arm();self.s.advance(.3);self.m.apply({'native_refill_skill_cooldown':False});self.s.advance(.4);self.s.advance(.5);self.assertEqual(self.calls+self.s.calls,[])
    def test_mode_change_in_getter(self):
        self.arm();self.s.advance(.3);lease=self.m._automation_leases['skill_cooldown'];old=lease.adaptive_api[0]
        def read(*a):
            v=old(*a);self.m.apply({'native_refill_skill_cooldown':False});return v
        lease.adaptive_api=(read,lease.adaptive_api[1]);self.s.advance(.4);self.assertEqual(self.calls,[])
    def test_overshoot_fault(self):
        self.effect=lambda i,a:self.s.val.__setitem__(i,1.);self.arm();self.trend();self.assertTrue(self.m.automation_fault());self.assertEqual(len(self.calls),1)
    def test_peer_change_fault(self):
        def effect(i,a):self.s.val[i]+=a;self.s.val[1-i]=.1
        self.effect=effect;self.arm();self.trend();self.assertTrue(self.m.automation_fault())
    def test_ineffective_no_retry(self):
        self.effect=lambda *a:None;self.arm();self.trend();self.s.advance(.5);self.s.advance(.6);self.assertEqual(len(self.calls),1);self.assertEqual(self.s.calls,[])
    def test_join(self):self.arm();self.s.advance(.3);self.s.b.f.players=2;self.s.advance(.4);self.assertEqual(self.calls,[])
    def test_stop_after_dispatch_fault(self):
        self.effect=lambda *a:self.m.request_stop('reentrant');self.arm();self.trend();self.assertTrue(self.m.automation_fault())
    def test_wrong_reference(self):
        from test_combat_r13 import typ
        self.refills[0]._properties()[0].Struct=typ(self.s.rt._path_name());self.arm();self.trend();self.assertEqual(self.calls+self.s.calls,[])
    def test_crossfire_conflict(self):
        import sys
        self.arm();self.s.advance(.3)
        name='infinite_crossfire';self.assertNotIn(name,sys.modules);sys.modules[name]=N()
        self.addCleanup(lambda:sys.modules.pop(name,None));self.s.advance(.4);self.assertEqual(self.calls,[])
    def test_both_independently(self):
        self.a.t.arm('cooldown','duration',**{prefix+'skill_'+mode:value for mode in ('cooldown','duration') for prefix,value in (('adaptive_',True),('native_refill_',True),('adaptive_rate_',2.))})
        self.s.advance(dt=.2);self.s.advance(.22,.78);self.s.advance(.24,.76);self.s.advance(.26,.74)
        self.assertEqual(sorted(c[0] for c in self.calls),[0,1]);self.assertEqual(self.s.calls,[])
