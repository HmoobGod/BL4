"""Synthetic persistent replacement admission; not native gameplay or rate proof."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Node,typ
from test_skill_pulse_r19 import Handle,Inline
from test_adaptive_skill_r43 import AdaptiveSkill

class SkillFollow(unittest.TestCase):
    def setUp(self):
        self.a=AdaptiveSkill();self.a.setUp();self.addCleanup(self.a.doCleanups)
        self.s=self.a.s;self.m=self.s.m;self.n=0;self.original=self.s.skill
    def arm(self,*modes,adaptive=False,follow=True):
        settings={'follow_skill_'+mode:follow for mode in modes}
        if adaptive:settings.update({'adaptive_skill_'+mode:True for mode in modes});settings.update({'adaptive_rate_skill_'+mode:2. for mode in modes})
        self.a.t.arm(*modes,**settings);self.s.advance(dt=.2)
    def replacement(self,same_guid=False,same_pool=False,charge=False,aux=False,foreign=False):
        s=self.s;self.n+=1;tag=str(self.n)
        old=(s.skill,s.script,s.g,s.h,s.defs,s.d,s.cls)
        s.g=s.g if same_guid else Node(_type=s.gt,A=10+self.n,B=2,C=3,D=4)
        s.h=[Handle(h._name if same_pool else tag+'_'+h._name) for h in s.h]
        s.defs=[Handle(tag+'_cooldown_def',resource=s.h[0]),Handle(tag+'_duration_def',resource=s.h[1])]
        s.d=Inline(_type=old[5]._type,ComponentID=s.g,ChargeComponentID=s.g if charge else s.zero,AuxCooldownPoolDefs=[s.defs[0]] if aux else [],CooldownPoolDef=s.defs[0],DurationPoolDef=s.defs[1])
        s.skill=Node(SkillOwner=s.p if not foreign else Node());s.cls=typ('BP_NewSkill_'+tag+'_C',parents=(typ('/Script/GbxGame.GbxSkillScript'),));s.cls.SkillComponents=[N(ComponentData=s.d)];s.cls.SkillComponentSets=[]
        s.script=Node(Class=s.cls,Skill=s.skill,Actor=s.p,bIsInitialized=True);s.skill.SkillScripts=[s.script];s.skills=[s.skill]
        return old
    def step(self,c=None,d=None,dt=1.):self.s.advance(c,d,dt)
    def lease(self,mode='cooldown'):return self.m._automation_leases.get('skill_'+mode)
    def test_default_off(self):
        self.assertTrue(all(not o.value for o in self.m.SKILL_FOLLOW.values()))
        self.arm('cooldown',follow=False);self.step(.3);self.replacement();self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_opt_in_does_not_arm(self):
        self.m.apply({'follow_skill_cooldown':True,'persistent_master':True,'persistent_offline':True});self.step(.3);self.step(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m._automation_leases)
    def test_cooldown_follows_after_two_samples_and_fresh_trend(self):
        self.arm('cooldown');lease=self.lease();self.step(.3);self.replacement();self.step(.4);self.assertIs(self.lease(),lease);self.assertIsNotNone(lease.follow_candidate);self.assertEqual(self.s.calls,[])
        self.step(.5);self.assertIsNone(lease.follow_candidate);self.assertEqual(self.s.calls,[]);self.step(.6);self.assertEqual(self.s.calls,[]);self.step(.7);self.assertEqual(len(self.s.calls),1)
    def test_adaptive_duration_follows(self):
        self.arm('duration',adaptive=True);self.step(d=.79);self.replacement();self.step(d=.78);self.step(d=.77);self.step(d=.76);self.assertEqual(self.s.calls,[]);self.step(d=.75);self.assertAlmostEqual(self.s.calls[0][1],.01);self.assertEqual(self.s.calls[0][0],1)
    def test_both_lanes(self):
        self.arm('cooldown','duration');self.step(.3,.7);self.replacement();self.step(.4,.6);self.step(.5,.5);self.step(.6,.4);self.assertEqual(self.s.calls,[]);self.step(.7,.3);self.assertEqual([c[0] for c in self.s.calls],[0,1])
    def test_charge_or_aux_replacement_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement(charge=True);self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_aux_replacement_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement(aux=True);self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_foreign_replacement_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement(foreign=True);self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_shared_pool_identity_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement(same_pool=True);self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_shared_guid_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement(same_guid=True);self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_original_returns(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.s.skills=[self.original];self.step(.5);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_third_candidate_refused(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.replacement();self.step(.5);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_expired_witness(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.step(.5,dt=3.);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_pending_old_refill_stops(self):
        self.arm('cooldown');self.step(.3);self.step(.4);self.assertEqual(len(self.s.calls),1);self.replacement();self.step(.5);self.assertIsNone(self.lease());self.assertEqual(len(self.s.calls),1)
    def test_join_mid_transition(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.s.b.f.players=2;self.step(.5);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_absent_does_not_retry(self):
        self.arm('cooldown');self.step(.3);self.s.skills=[];self.step(.4);self.assertIsNone(self.lease());self.replacement();self.step(.5);self.step(.6);self.assertEqual(self.s.calls,[])
    def test_follow_preference_change_stops(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.m.set_auto_setting(self.m.SKILL_FOLLOW['skill_cooldown'],False);self.step(.5);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_manual_does_not_follow(self):
        self.m.apply({'follow_skill_cooldown':True});self.s.start();self.step(.3);self.replacement();self.step(.4);self.assertFalse(self.m.health_active());self.assertEqual(self.s.calls,[])
    def test_late_inline_component_mutation_stops(self):
        self.s.start();self.step(.3);lease=self.m._health_pulse;old=lease.api[2];count=0
        def read(*args):
            nonlocal count
            count+=1;value=old(*args)
            if count==4:self.s.d.ComponentID=Node(_type=self.s.gt,A=99,B=2,C=3,D=4)
            return value
        lease.api=(*lease.api[:2],read,lease.api[3]);self.step(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m.health_active())
    def test_late_membership_mutation_stops(self):
        self.s.start();self.step(.3);lease=self.m._health_pulse;old=lease.api[2];count=0
        def read(*args):
            nonlocal count
            count+=1;value=old(*args)
            if count==4:self.s.skills=[]
            return value
        lease.api=(*lease.api[:2],read,lease.api[3]);self.step(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m.health_active())
    def test_follow_change_during_getter_stops(self):
        self.arm('cooldown');self.step(.3);self.replacement();lease=self.lease();old=lease.api[0]
        def read(*args):
            value=old(*args);self.m.apply({'follow_skill_cooldown':False});return value
        lease.api=(read,*lease.api[1:]);self.step(.4);self.assertEqual(self.s.calls,[]);self.assertIsNone(self.lease())
    def test_adaptive_mismatch_replacement_stops(self):
        self.arm('cooldown',adaptive=True);self.step(.3);self.replacement();self.a.override['GetCooldownAsPercentInternal']=.9;self.step(.4);self.assertIsNone(self.lease());self.assertEqual(self.s.calls,[])
    def test_status_wait_and_rearm(self):
        self.arm('cooldown');self.step(.3);self.replacement();self.step(.4);self.assertIn('Waiting:',self.m._automation_status['skill_cooldown']);self.step(.5);self.assertIn('Armed',self.m._automation_status['skill_cooldown'])
    def test_external_replacement(self):
        from test_combat_r13 import desc,arraydesc
        from bl4_custom_foundation.skill_pulse import SET_CLASS,SET_ENTRY
        self.arm('cooldown');self.step(.3);self.replacement();s=self.s
        entry=typ(SET_ENTRY);cls=typ(SET_CLASS,arraydesc('Components',desc('Element',entry)))
        asset=Node(Name='/Game/Test/Replacement.Replacement',Class=cls,Components=[Node(_type=entry,ComponentData=s.d)])
        inner=type('ZSoftObjectProperty',(),{'PropertyClass':cls})()
        s.cls._properties=lambda:[arraydesc('SkillComponentSets',inner)];s.cls.SkillComponents=[];s.cls.SkillComponentSets=[asset]
        # The SDK resolver is captured at arm; update the existing test lease with a synthetic adapter.
        self.lease().soft_identifier=lambda arr,i:asset.Name
        self.step(.4);self.step(.5);self.step(.6);self.step(.7);self.assertEqual(len(s.calls),1)
