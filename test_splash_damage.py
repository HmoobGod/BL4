"""Synthetic local splash multiplier tests; no native gameplay claims."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class SplashDamage(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.p=self.c.p;self.splash=attr(2.);self.radius=attr(3.);self.normal=attr(1.);self.crit=attr(2.)
        self.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter';self.p._path_name=lambda:'/Game/Test.Pawn'
        self.splash._type._path_name=lambda:'/Script/GbxCore.GbxAttributeFloat'
        self.data=Node(RadiusDamage_DamageMultiplier=self.splash,RadiusDamage_RadiusMultiplier=self.radius,DamageDealtMultiplier=self.normal,DefaultCriticalHitMultiplier=self.crit,_type=typ('OakDamageCauserData',desc('RadiusDamage_DamageMultiplier',self.splash._type)))
        self.data._type._path_name=lambda:'/Script/OakGame.OakDamageCauserData'
        self.p.DamageCauserData=self.data;prior=self.p.Class._properties();self.p.Class._properties=lambda:prior+[desc('DamageCauserData',self.data._type)]
    def apply(self,v):self.c.activate('splash_damage',v)
    def vals(self):return self.c.vals(self.splash)
    def test_manual_default(self):
        self.assertNotIn('splash_damage',self.m.AUTO_OPTIONS);self.assertEqual(self.m._PREVIEW_BY_KEY['splash_damage'].value,1.);self.assertEqual(self.splash.writes,[])
    def test_cycle(self):
        self.apply(2.);self.assertEqual(self.vals(),(4.,4.));self.apply(3.);self.assertEqual(self.vals(),(6.,6.));self.apply(1.);self.assertEqual(self.vals(),(2.,2.));self.assertEqual(self.radius.writes+self.normal.writes+self.crit.writes,[])
    def test_reduce(self):self.apply(.5);self.assertEqual(self.vals(),(1.,1.))
    def test_neutral(self):self.apply(1.);self.assertEqual(self.splash.writes,[])
    def test_mismatched_baseline(self):self.splash._values['Value']=3.;self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_zero_baseline(self):self.splash._values.update(Value=0.,BaseValue=0.);self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_wrong_pawn(self):self.p.Class._path_name=lambda:'/Script/Other.OakCharacter';self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_wrong_struct(self):self.data._type._path_name=lambda:'/Script/Other.OakDamageCauserData';self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_wrong_pair(self):self.splash._type._path_name=lambda:'/Script/Other.GbxAttributeFloat';self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_bound(self):self.splash._values.update(Value=6.,BaseValue=6.);self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_join_restores(self):self.apply(2.);self.c.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.vals(),(2.,2.))
    def test_partial_write(self):self.splash.raise_after='Value';self.apply(2.);self.assertEqual(self.vals(),(2.,2.));self.assertFalse(self.m._controller.records)
    def test_foreign_drift(self):self.apply(2.);self.splash._values['Value']=5.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.splash.Value,5.)
    def test_stop(self):self.apply(2.);self.m.request_stop('test',immediate=True);self.assertEqual(self.vals(),(2.,2.))

    def test_other_modifier_blocks_splash(self):
        self.c.activate('fire_rate',2.);self.assertIn('fire_rate',self.m._controller.records);self.apply(2.);self.assertEqual(self.splash.writes,[])
    def test_splash_blocks_other_modifier(self):
        self.apply(2.);self.c.activate('fire_rate',2.);self.assertNotIn('fire_rate',self.m._controller.records);self.assertEqual(self.vals(),(4.,4.))
