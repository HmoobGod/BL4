"""Synthetic local overshield duration experiment, not native gameplay."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class Overshield(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.p=self.c.p;self.duration=attr(10.);self.base=attr(50.)
        self.p._path_name=lambda:"/Game/Test.LocalPawn"
        self.manager=Node(OvershieldDuration=self.duration,OvershieldBaseValue=self.base,
            _type=typ('OakOvershieldManager',desc('OvershieldDuration',self.duration._type),desc('OvershieldBaseValue',self.base._type)))
        self.manager._type._path_name=lambda:'/Script/OakGame.OakOvershieldManager'
        self.p.OvershieldManager=self.manager
        prior=self.p.Class._properties();self.p.Class._properties=lambda:prior+[desc('OvershieldManager',self.manager._type)]
    def apply(self,v):self.c.activate('overshield_duration',v)
    def set(self,obj,v):obj._values.update(Value=v,BaseValue=v)
    def test_default_manual(self):
        self.assertNotIn('overshield_duration',self.m.AUTO_OPTIONS)
        self.assertEqual(self.m._PREVIEW_BY_KEY['overshield_duration'].value,1.)
        self.assertEqual(self.duration.writes,[])
    def test_neutral(self):self.apply(1.);self.assertEqual(self.duration.writes,[])
    def test_update_restore(self):
        self.apply(2.);self.assertEqual(self.c.vals(self.duration),(20.,20.))
        self.apply(3.);self.assertEqual(self.c.vals(self.duration),(30.,30.))
        self.apply(1.);self.assertEqual(self.c.vals(self.duration),(10.,10.));self.assertEqual(self.base.writes,[])
    def test_reduce(self):self.apply(.5);self.assertEqual(self.c.vals(self.duration),(5.,5.))
    def test_no_seed_duration(self):self.set(self.duration,0.);self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_no_seed_base(self):self.set(self.base,0.);self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_base_uncertain(self):self.base._values['Value']=51.;self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_duration_uncertain(self):self.duration._values['Value']=11.;self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_bounded(self):self.set(self.duration,70.);self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_wrong_path(self):self.manager._type._path_name=lambda:'/Script/Other.OakOvershieldManager';self.apply(2.);self.assertEqual(self.duration.writes,[])
    def test_base_drift_restores(self):
        self.apply(2.);self.set(self.base,60.);self.m.monitor_tick();self.assertEqual(self.c.vals(self.duration),(10.,10.));self.assertEqual(self.base.writes,[])
    def test_base_loss_restores(self):
        self.apply(2.);self.set(self.base,0.);self.m.monitor_tick();self.assertEqual(self.c.vals(self.duration),(10.,10.))
    def test_foreign_duration(self):
        self.apply(2.);self.duration._values['Value']=21.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.duration.Value,21.)
    def test_failed_pair_rolls_back(self):
        self.duration.raise_after='Value';self.apply(2.);self.assertEqual(self.c.vals(self.duration),(10.,10.))
    def test_join_restores(self):
        self.apply(2.);self.c.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.c.vals(self.duration),(10.,10.))
    def test_stop_restores(self):
        self.apply(2.);self.m.request_stop('test',immediate=True);self.assertEqual(self.c.vals(self.duration),(10.,10.))
