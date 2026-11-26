"""Synthetic skill pool fixtures, not native runtime proof."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Combat,Node,typ,desc,objdesc

class Handle(Node):
    def __init__(self,name,**kw):super().__init__(_name=name,_type_handle=1,**kw)
class Inline(Node):pass
class SkillPulseTests(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.p=self.c.p;self.b=self.c.b;self.now=100.;self.calls=[];self.val=[.2,.8]
        self.m.time=N(monotonic=lambda:self.now);self.p.HealthCondition=N(name='Healthy')
        from bl4_custom_foundation.skill_pulse import SkillPulse,bind,SPECS,PATH,REF
        self.Pulse=SkillPulse;self.bind=bind;self.SPECS=SPECS
        self.gt=typ('/Script/CoreUObject.Guid');self.g=Node(_type=self.gt,A=1,B=2,C=3,D=4);self.zero=Node(_type=self.gt,A=0,B=0,C=0,D=0)
        self.h=[Handle('cooldown_resource'),Handle('duration_resource')];self.defs=[Handle('cooldown_def',resource=self.h[0]),Handle('duration_def',resource=self.h[1])]
        self.d=Inline(_type=typ('/Script/OakGame.GbxSkillComponentData_ActionSkill',parents=(typ('/Script/GbxGame.GbxSkillComponentData'),)),ComponentID=self.g,ChargeComponentID=self.zero,AuxCooldownPoolDefs=[],CooldownPoolDef=self.defs[0],DurationPoolDef=self.defs[1])
        self.skill=Node(SkillOwner=self.p);self.cls=typ('BP_Skill_C',parents=(typ('/Script/GbxGame.GbxSkillScript'),));self.cls.SkillComponentSets=[];self.cls.SkillComponents=[N(ComponentData=self.d)]
        self.script=Node(Class=self.cls,Skill=self.skill,Actor=self.p,bIsInitialized=True);self.skill.SkillScripts=[self.script];self.skills=[self.skill]
        self.rt=typ(REF,objdesc('Context','/Script/GbxGame.GbxSkillScript'),desc('ComponentID',self.gt))
        self.api=(lambda r,h:self.val[self.h.index(h)],lambda r,h:self.val[self.h.index(h)]*100,lambda r,h:100.,self.refill)
        u=self.b.f.sdk.unreal;u.FGameDataHandle=Handle;u.WrappedInlineStruct=Inline;u.WrappedStruct=lambda t,**kw:Node(_type=t,**kw)
        self.funcs=[]
        for (name,sig),call in zip(SPECS.items(),self.api,strict=True):
            path=PATH+name;props=[type(k,(),{'Name':n,'ArrayDim':1})() for n,k in sig];props[0].Struct=self.rt
            cdo=N();owner=N(_path_name=lambda:PATH[:-1],ClassDefaultObject=cdo)
            f=N(Name=name,Outer=owner,NumParams=len(props),_path_name=lambda path=path:path,_properties=lambda props=props:props)
            def bound(*a,call=call):return call(*a)
            bound.func=f;setattr(cdo,name,bound);self.funcs.append(f)
        old=self.b.f.sdk.find_all
        self.b.f.sdk.find_all=lambda *a,**k:list(old(*a,**k))+self.funcs if a[0]=='Function' else self.skills if a[0]=='GbxSkill' else old(*a,**k)
    def refill(self,r,h,amount,cap):
        self.assertIs(r.Context,self.script);self.assertIs(r.ComponentID,self.g);i=self.h.index(h);self.calls.append((i,amount,cap));self.val[i]=min(cap,self.val[i]+amount)
    def start(self,mode='cooldown'):self.m.activate_feature('skill_'+mode,1.);self.m.monitor_tick()
    def advance(self,c=None,d=None,dt=1.):
        if c is not None:self.val[0]=c
        if d is not None:self.val[1]=d
        self.now+=dt;self.m.monitor_tick()
    def test_cooldown(self):
        self.start();self.assertTrue(self.m.health_active());self.advance(.3);self.advance(.4);self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][0],0);self.assertAlmostEqual(self.val[0],.41);self.assertEqual(self.val[1],.8)
    def test_duration(self):
        self.start('duration');self.advance(d=.7);self.advance(d=.6);self.assertEqual(self.calls[0][0],1);self.assertAlmostEqual(self.val[1],.61);self.assertEqual(self.val[0],.2)
    def test_flat_and_wrong_direction(self):self.start();self.advance(.1);self.advance(.1);self.advance(.2);self.assertEqual(self.calls,[])
    def test_charge(self):self.d.ChargeComponentID=self.g;self.start();self.assertFalse(self.m.health_active())
    def test_aux(self):self.d.AuxCooldownPoolDefs=[self.defs[0]];self.start();self.assertFalse(self.m.health_active())
    def test_duplicate_guid(self):self.cls.SkillComponents.append(N(ComponentData=self.d));self.start();self.assertFalse(self.m.health_active())
    def test_foreign_script(self):self.script.Actor=Node();self.start();self.assertFalse(self.m.health_active())
    def test_external_set(self):self.cls.SkillComponentSets=[Node()];self.start();self.assertFalse(self.m.health_active())
    def test_alias(self):self.defs[1].resource=self.h[0];self.start();self.assertFalse(self.m.health_active())
    def test_join(self):self.start();self.advance(.3);self.b.f.players=2;self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_replacement(self):self.start();self.advance(.3);self.d.ComponentID=Node(_type=self.gt,A=9,B=2,C=3,D=4);self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_skill_removed(self):self.start();self.advance(.3);self.skills=[];self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_lifetime(self):self.start();self.advance(.3);self.advance(.4,dt=30);self.assertEqual(self.calls,[])
    def test_stop(self):self.start();self.advance(.3);self.m.request_stop('owner');self.advance(.4);self.assertEqual(self.calls,[])
    def test_skip_own_sample(self):self.start();self.advance(.3);self.advance(.4);self.advance(.5);self.advance(.6);self.assertEqual(len(self.calls),1);self.advance(.7);self.assertEqual(len(self.calls),2)
    def test_injured(self):self.p.HealthCondition=N(name='Injured');self.start();self.assertFalse(self.m.health_active())
    def test_no_effect(self):self.start();a=self.m._health_pulse;a.api=(*a.api[:3],lambda *x:None);self.advance(.3);self.advance(.4);self.assertFalse(self.m.health_active())
    def test_fault(self):
        self.start();a=self.m._health_pulse;a.api=(*a.api[:3],lambda *x:(_ for _ in ()).throw(RuntimeError()));self.advance(.3);self.advance(.4);self.assertTrue(self.m.health_fault());self.assertFalse(self.m.health_active())
    def test_binding(self):self.funcs.pop();self.start();self.assertFalse(self.m.health_active())
    def test_f8(self):self.m._category=6;self.b.gui.imgui.clicks={'Start experimental skill cooldown assist (30 sec)'};self.m.draw();self.assertFalse(self.m.health_active());self.m.monitor_tick();self.assertTrue(self.m.health_active())

    def test_readback_over_cap_fault(self):
        self.start();a=self.m._health_pulse
        def over(*args):self.val[0]=.8
        a.api=(*a.api[:3],over);self.advance(.3);self.advance(.4);self.assertTrue(self.m.health_fault())
    def test_reentrant_stop_before_dispatch(self):
        self.start();a=self.m._health_pulse;self.advance(.3);old=a.api[0]
        def read(*args):self.m.request_stop('reentrant');return old(*args)
        a.api=(read,*a.api[1:]);self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_pool_replaced(self):
        self.start();self.advance(.3);self.defs[0].resource=Handle('replacement');self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_same_name_distinct_handle(self):
        self.defs[1].resource=Handle(self.h[0]._name);self.start();self.assertFalse(self.m.health_active())
    def test_inherited_definition(self):
        base=typ('/Script/GbxGame.GbxSkillScript');base.SkillComponents=[N(ComponentData=self.d)];base.SkillComponentSets=[];self.cls._superfields=lambda:iter((base,));self.start();self.assertFalse(self.m.health_active())
    def test_other_modifier_excluded(self):self.c.activate('jump',1.5);self.start();self.assertFalse(self.m.health_active())
    def test_unique_inherited_component_r20(self):
        base=typ('/Script/GbxGame.GbxSkillScript');base.SkillComponents=[N(ComponentData=self.d)];base.SkillComponentSets=[];self.cls._superfields=lambda:iter((base,));self.cls.SkillComponents=[];self.start();self.assertTrue(self.m.health_active());self.advance(.3);self.advance(.4);self.assertEqual(len(self.calls),1)
    def test_inherited_origin_change_r20(self):
        base=typ('/Script/GbxGame.GbxSkillScript');base.SkillComponents=[];base.SkillComponentSets=[];self.cls._superfields=lambda:iter((base,));self.start();self.advance(.3);base.SkillComponents=self.cls.SkillComponents;self.cls.SkillComponents=[];self.advance(.4);self.assertEqual(self.calls,[]);self.assertFalse(self.m.health_active())
    def test_inherited_external_set_r20(self):
        base=typ('/Script/GbxGame.GbxSkillScript');base.SkillComponents=[];base.SkillComponentSets=[Node()];self.cls._superfields=lambda:iter((base,));self.start();self.assertFalse(self.m.health_active())
