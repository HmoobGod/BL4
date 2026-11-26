"""Named primary cooldown follow: synthetic, not actual game validation."""
import unittest
from types import SimpleNamespace as N
from test_requested_named_cooldown import NamedCooldown
from test_skill_pulse_r19 import Handle, Inline
from test_combat_r13 import Node, typ

class NamedFollow(unittest.TestCase):
    def setUp(self):
        self.f=NamedCooldown();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.s=self.f.s;self.m=self.f.m;self.original=self.s.skill;self.n=0
        self.oldaux=self.f.aux;self.oldcharge=self.f.ch
    def arm(self,**kw):self.f.arm(follow_skill_cooldown=True,**kw)
    def lease(self):return self.m._automation_leases.get('skill_cooldown')
    def calls(self):return self.f.direct+self.f.n.calls+self.s.calls
    def advance(self,p):self.s.advance(p)
    def replace(self,named=True,charge=False,alias=None):
        s=self.s;self.n+=1;n=self.n
        s.g=Node(_type=s.gt,A=20+n,B=2,C=3,D=4)
        s.h=[Handle('Resource_DarkSiren_ActionSkill_PhaseFamiliar_Cooldown' if named else 'ordinary_new_cooldown'),Handle('new_duration_'+str(n))]
        s.defs=[Handle('new_cooldown_def_'+str(n),resource=s.h[0]),Handle('new_duration_def_'+str(n),resource=s.h[1])]
        for h in s.defs:h._type_handle=2
        aux=Handle('new_aux_'+str(n));auxdef=Handle('new_auxdef_'+str(n),resource=aux);auxdef._type_handle=2
        ch=Handle('new_charge_'+str(n));cg=Node(_type=s.gt,A=30+n,B=2,C=3,D=4)
        if alias=='name':aux._name=self.oldaux._name.upper()
        if alias=='address':aux=self.oldaux;auxdef.resource=aux
        if alias=='charge_guid':cg=self.f.cg
        if alias=='old_main':s.h[0]._name='Resource_DarkSiren_ActionSkill_PhaseShard_Cooldown'
        self.f.values[aux._name]=.4;self.f.values[ch._name]=.5
        s.d=Inline(_type=s.d._type,ComponentID=s.g,ChargeComponentID=cg if charge else s.zero,AuxCooldownPoolDefs=[auxdef] if named else [],CooldownPoolDef=s.defs[0],DurationPoolDef=s.defs[1])
        s.cls=typ('BP_Distinct_'+str(n)+'_C',parents=(typ('/Script/GbxGame.GbxSkillScript'),));s.cls.SkillComponents=[N(ComponentData=s.d)];s.cls.SkillComponentSets=[]
        if charge:s.cls.SkillComponents.append(N(ComponentData=Inline(_type=self.f.charge._type,ComponentID=cg,ChargePoolHandle=ch)))
        s.skill=Node(SkillOwner=s.p);s.script=Node(Class=s.cls,Skill=s.skill,Actor=s.p,bIsInitialized=True);s.skill.SkillScripts=[s.script];s.skills=[s.skill]
        return aux,ch
    def witness(self):self.advance(.4);self.assertIsNotNone(self.lease().follow_candidate);self.assertFalse(self.calls());self.advance(.41);self.assertIsNone(self.lease().follow_candidate);self.assertFalse(self.calls());self.advance(.42);self.assertFalse(self.calls());self.advance(.43)
    def test_named_to_named(self):
        self.f.add_charge();self.arm();self.advance(.21);aux,ch=self.replace(charge=True);self.witness();self.assertEqual(len(self.f.direct),1);self.assertEqual(self.f.n.calls,[]);self.assertEqual(self.f.values[aux._name],.4);self.assertEqual(self.f.values[ch._name],.5)
    def test_ordinary_to_named(self):
        self.s.d.AuxCooldownPoolDefs=[];self.arm();self.advance(.21);self.replace();self.witness();self.assertEqual(len(self.f.direct),1);self.assertEqual(self.lease().named_max,100.)
    def test_named_to_ordinary(self):
        self.arm();self.advance(.21);self.replace(named=False);self.witness();self.assertEqual(self.f.direct,[]);self.assertEqual(len(self.f.n.calls),1);self.assertIsNone(self.lease().named_max)
    def test_excluded_pool_case_alias(self):
        self.arm();self.advance(.21);self.replace(alias='name');self.advance(.4);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_excluded_pool_address_alias(self):
        self.arm();self.advance(.21);self.replace(alias='address');self.advance(.4);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_charge_guid_reuse(self):
        self.f.add_charge();self.arm();self.advance(.21);self.replace(charge=True,alias='charge_guid');self.advance(.4);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_main_pool_reuse(self):
        self.arm();self.advance(.21);self.replace(alias='old_main');self.advance(.4);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_join_during_witness(self):
        self.arm();self.advance(.21);self.replace();self.advance(.4);self.s.b.f.players=2;self.advance(.41);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_replacement_after_pending_direct(self):
        self.arm();self.f.trend();self.assertEqual(len(self.f.direct),1);self.replace();self.advance(.4);self.assertIsNone(self.lease());self.assertEqual(len(self.calls()),1)
    def test_second_witness_max_change(self):
        self.arm();self.advance(.21);self.replace();self.advance(.4);lease=self.lease();a=lease.api;direct=lease.direct_api
        lease.api=(a[0],lambda r,h:a[1](r,h)*2.,lambda r,h:a[2](r,h)*2.,a[3]);lease.direct_api=(lambda p,h:direct[0](p,h)*2.,*direct[1:]);self.advance(.41);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_peer_replacement_between_witnesses(self):
        self.arm();self.advance(.21);self.replace();self.advance(.4);h=Handle('new_aux_during_witness');self.f.values[h._name]=.4;self.s.d.AuxCooldownPoolDefs[0].resource=h;self.advance(.41);self.assertIsNone(self.lease());self.assertFalse(self.calls())
    def test_direct_missing_preserves_ordinary_only(self):
        self.s.d.AuxCooldownPoolDefs=[];self.s.funcs.remove(self.f.funcs[-1]);self.arm();self.advance(.21);self.replace();self.advance(.4);self.assertIsNone(self.lease());self.assertFalse(self.calls())
