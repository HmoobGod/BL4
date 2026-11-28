"""Synthetic default chance bonus tests; no native chance claims."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class CriticalChance(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.m=self.c.m; self.p=self.c.p; self.chance=attr(0.); self.damage=attr(2.)
        self.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter'; self.p._path_name=lambda:'/Game/Test.Pawn'
        self.chance._type._path_name=lambda:'/Script/GbxCore.GbxAttributeFloat'
        self.data=Node(DefaultCriticalHitChance=self.chance,DefaultCriticalHitMultiplier=self.damage,_type=typ('OakDamageCauserData',desc('DefaultCriticalHitChance',self.chance._type)))
        self.data._type._path_name=lambda:'/Script/OakGame.OakDamageCauserData'
        self.p.DamageCauserData=self.data; prior=self.p.Class._properties(); self.p.Class._properties=lambda:prior+[desc('DamageCauserData',self.data._type)]
    def apply(self,v): self.c.activate('critical_chance',v)
    def vals(self): return self.c.vals(self.chance)
    def test_default(self):
        self.assertNotIn('critical_chance',self.m.AUTO_OPTIONS); self.assertEqual(self.m._PREVIEW_BY_KEY['critical_chance'].value,1.); self.assertEqual(self.chance.writes,[])
    def test_zero_cycle(self):
        self.apply(11.); self.assertAlmostEqual(self.vals()[0],.1); self.assertEqual(*self.vals()); self.apply(21.); self.assertAlmostEqual(self.vals()[0],.2); self.apply(1.); self.assertEqual(self.vals(),(0.,0.)); self.assertEqual(self.damage.writes,[])
    def test_positive_baseline(self):
        self.chance._values.update(Value=.25,BaseValue=.25); self.apply(21.); self.assertAlmostEqual(self.vals()[0],.45); self.apply(1.); self.assertEqual(self.vals(),(.25,.25))
    def test_cap(self):
        self.chance._values.update(Value=.625,BaseValue=.625); self.apply(21.); self.assertEqual(self.chance.writes,[])
    def test_fractional_refused(self): self.apply(11.5); self.assertEqual(self.chance.writes,[])
    def test_neutral(self): self.apply(1.); self.assertEqual(self.chance.writes,[])
    def test_invalid_baseline(self): self.chance._values.update(Value=-.1,BaseValue=-.1); self.apply(11.); self.assertEqual(self.chance.writes,[])
    def test_mismatch(self): self.chance._values['Value']=.1; self.apply(11.); self.assertEqual(self.chance.writes,[])
    def test_wrong_struct(self): self.data._type._path_name=lambda:'/Script/Other.OakDamageCauserData'; self.apply(11.); self.assertEqual(self.chance.writes,[])
    def test_wrong_pawn(self): self.p.Class._path_name=lambda:'/Script/Other.OakCharacter'; self.apply(11.); self.assertEqual(self.chance.writes,[])
    def test_join(self): self.apply(11.); self.c.b.f.players=2; self.m.monitor_tick(); self.assertEqual(self.vals(),(0.,0.))
    def test_partial_write(self): self.chance.raise_after='Value'; self.apply(11.); self.assertEqual(self.vals(),(0.,0.)); self.assertFalse(self.m._controller.records)
    def test_foreign_drift(self): self.apply(11.); self.chance._values['Value']=.5; self.m.monitor_tick(); self.assertTrue(self.m._controller.fault); self.assertEqual(self.chance.Value,.5)
    def test_other_blocks(self): self.c.activate('fire_rate',2.); self.apply(11.); self.assertEqual(self.chance.writes,[])
    def test_blocks_other(self): self.apply(11.); self.c.activate('fire_rate',2.); self.assertNotIn('fire_rate',self.m._controller.records)
