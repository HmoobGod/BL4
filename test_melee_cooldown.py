"""Synthetic local melee cooldown ownership and inverse scaling tests."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class MeleeCooldown(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.p=self.c.p;self.cool=attr(1.);self.play=attr(1.)
        self.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter';self.p._path_name=lambda:'/Game/Test.Pawn'
        self.cool._type._path_name=lambda:'/Script/GbxCore.GbxAttributeFloat'
        self.state=Node(CooldownScale=self.cool,PlayRate=self.play,_type=typ('OakMeleeState',desc('CooldownScale',self.cool._type)))
        self.state._type._path_name=lambda:'/Script/OakGame.OakMeleeState'
        self.p.MeleeState=self.state;prior=self.p.Class._properties();self.p.Class._properties=lambda:prior+[desc('MeleeState',self.state._type)]
    def apply(self,v):self.c.activate('melee_cooldown',v)
    def vals(self):return self.c.vals(self.cool)
    def test_default_manual(self):
        self.assertNotIn('melee_cooldown',self.m.AUTO_OPTIONS);self.assertEqual(self.m._PREVIEW_BY_KEY['melee_cooldown'].value,1.);self.assertEqual(self.cool.writes,[])
    def test_inverse_cycle(self):
        self.apply(2.);self.assertEqual(self.vals(),(.5,.5));self.apply(.5);self.assertEqual(self.vals(),(2.,2.));self.apply(1.);self.assertEqual(self.vals(),(1.,1.));self.assertEqual(self.play.writes,[])
    def test_neutral(self):self.apply(1.);self.assertEqual(self.cool.writes,[])
    def test_baseline_mismatch(self):self.cool._values['Value']=.75;self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_zero(self):self.cool._values.update(Value=0.,BaseValue=0.);self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_bounds(self):self.cool._values.update(Value=3.,BaseValue=3.);self.apply(.5);self.assertEqual(self.cool.writes,[])
    def test_wrong_pawn(self):self.p.Class._path_name=lambda:'/Script/Other.OakCharacter';self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_wrong_state(self):self.state._type._path_name=lambda:'/Script/Other.OakMeleeState';self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_wrong_pair(self):self.cool._type._path_name=lambda:'/Script/Other.GbxAttributeFloat';self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_join_restores(self):self.apply(2.);self.c.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.vals(),(1.,1.))
    def test_partial_write(self):self.cool.raise_after='Value';self.apply(2.);self.assertEqual(self.vals(),(1.,1.));self.assertFalse(self.m._controller.records)
    def test_foreign_drift(self):self.apply(2.);self.cool._values['Value']=.8;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.cool.Value,.8)
    def test_stop(self):self.apply(2.);self.m.request_stop('test',immediate=True);self.assertEqual(self.vals(),(1.,1.))
    def test_other_modifier_blocks(self):self.c.activate('fire_rate',2.);self.assertIn('fire_rate',self.m._controller.records);self.apply(2.);self.assertEqual(self.cool.writes,[])
    def test_melee_blocks_other(self):self.apply(2.);self.c.activate('fire_rate',2.);self.assertNotIn('fire_rate',self.m._controller.records);self.assertEqual(self.vals(),(.5,.5))
