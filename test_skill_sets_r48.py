"""Synthetic resolved external skill-set admission; not native game evidence."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Node,typ,desc,arraydesc
from test_adaptive_skill_r43 import AdaptiveSkill

class ExternalSkillSets(unittest.TestCase):
    def setUp(self):
        self.a=AdaptiveSkill();self.a.setUp();self.addCleanup(self.a.doCleanups)
        self.s=self.a.s;self.m=self.s.m
        from bl4_custom_foundation.skill_pulse import SET_CLASS,SET_ENTRY
        self.entry=typ(SET_ENTRY)
        self.setcls=typ(SET_CLASS,arraydesc('Components',desc('Element',self.entry)))
        self.asset=Node(Name='/Game/Test/ExternalSet.ExternalSet',Class=self.setcls,Components=[Node(_type=self.entry,ComponentData=self.s.d)])
        self.inner=type('ZSoftObjectProperty',(),{'PropertyClass':self.setcls})()
        self.s.cls._properties=lambda:[arraydesc('SkillComponentSets',self.inner)]
        self.s.cls.SkillComponents=[];self.s.cls.SkillComponentSets=[self.asset]
        self.paths=[self.asset.Name]
        self.u=self.s.b.f.sdk.unreal
        self.u.ZSoftObjectProperty=N(_get_identifier_from_array=lambda arr,i:self.paths[i])
    def manual(self,mode='cooldown'):
        self.s.start(mode);self.assertTrue(self.m.health_active())
    def pulse(self):
        self.s.advance(.3);self.s.advance(.4)
    def hold(self):
        self.s.start();self.assertFalse(self.m.health_active());self.pulse();self.assertEqual(self.s.calls,[])
    def test_loaded_external_manual_cooldown(self):
        self.manual();self.pulse();self.assertEqual(len(self.s.calls),1);self.assertEqual(self.s.calls[0][0],0)
    def test_loaded_external_manual_duration(self):
        self.manual('duration');self.s.advance(d=.7);self.s.advance(d=.6);self.assertEqual(self.s.calls[0][0],1)
    def test_persistent_and_adaptive(self):
        self.a.arm();self.s.advance(.21);self.s.advance(.22);self.assertAlmostEqual(self.s.calls[0][1],.01)
    def test_unresolved_no_load(self):
        self.s.cls.SkillComponentSets=[None];self.hold()
    def test_missing_identifier_api(self):
        del self.u.ZSoftObjectProperty;self.hold()
    def test_wrong_path(self):
        self.paths=['/Game/Test/Other.Other'];self.hold()
    def test_wrong_class(self):
        self.asset.Class=typ('/Script/GbxGame.Other');self.hold()
    def test_wrong_entry(self):
        self.asset.Components[0]._type=typ('/Script/GbxGame.Other');self.hold()
    def test_duplicate_external(self):
        self.s.cls.SkillComponentSets.append(self.asset);self.paths.append(self.asset.Name);self.hold()
    def test_inline_duplicate_guid(self):
        self.s.cls.SkillComponents=[N(ComponentData=self.s.d)];self.hold()
    def test_charge_still_refused(self):
        self.s.d.ChargeComponentID=self.s.g;self.hold()
    def test_aux_still_refused(self):
        self.s.d.AuxCooldownPoolDefs=[self.s.defs[0]];self.hold()
    def test_replaced_asset_stops(self):
        self.manual();self.s.advance(.3);self.s.cls.SkillComponentSets=[Node(Name=self.asset.Name,Class=self.setcls,Components=self.asset.Components)];self.s.advance(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m.health_active())
    def test_unloaded_after_arm(self):
        self.manual();self.s.advance(.3);self.s.cls.SkillComponentSets=[None];self.s.advance(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m.health_active())
    def test_join(self):
        self.manual();self.s.advance(.3);self.s.b.f.players=2;self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_external_inherited(self):
        base=typ('/Script/GbxGame.GbxSkillScript',arraydesc('SkillComponentSets',self.inner));base.SkillComponents=[];base.SkillComponentSets=[self.asset]
        self.s.cls.SkillComponentSets=[];self.s.cls._superfields=lambda:iter((base,));self.manual();self.pulse();self.assertEqual(len(self.s.calls),1)
    def test_descriptor_wrong(self):
        self.inner.PropertyClass=typ('/Script/GbxGame.Other');self.hold()
    def test_set_removed_during_final_getter(self):
        self.manual();self.s.advance(.3);lease=self.m._health_pulse;old=lease.api[2];count=0
        def read(*args):
            nonlocal count
            count+=1
            value=old(*args)
            if count==4:self.s.cls.SkillComponentSets=[None]
            return value
        lease.api=(*lease.api[:2],read,lease.api[3]);self.s.advance(.4)
        self.assertEqual(self.s.calls,[]);self.assertFalse(self.m.health_active())
