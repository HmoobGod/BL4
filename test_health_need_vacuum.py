"""Synthetic health-aware collection; no native gameplay."""
import unittest
from test_vacuum_r25 import VacuumTests
from test_health_pulse_r17 import HealthPulse

class HealthNeedVacuumTests(VacuumTests):
    def setup_health(self,reader,others=()):
        self.actors=[self.drop('health','health',(300,0,0)),*others]
        self.assertTrue(self.start(('health','cash','ammo')))
        self.lease.health_reader=reader
    def test_full_preserved_until_injured(self):
        ratio=[1.];self.setup_health(lambda p:(('flesh',1,2),ratio[0]));self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
        ratio[0]=.4;self.tick();self.assertEqual([c[0] for c in self.calls],['health'])
    def test_unknown_health_skips_only_health(self):
        self.setup_health(lambda p:None,[self.drop('cash','cash',(400,0,0))]);self.tick();self.assertEqual([c[0] for c in self.calls],['cash'])
    def test_invalid_ratios(self):
        for ratio in (0.,-1.,1.01,True,float('nan')):
            self.setup_health(lambda p:(('flesh',1,2),ratio));self.tick();self.assertFalse(self.calls)
    def test_full_before_dispatch(self):
        vals=iter((.3,1.));self.setup_health(lambda p:(('flesh',1,2),next(vals)));self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
    def test_layer_replaced(self):
        keys=iter((('flesh',1,2),('flesh',1,3)));self.setup_health(lambda p:(next(keys),.3));self.tick();self.assertFalse(self.calls)
    def test_lost_read(self):
        vals=iter(((('flesh',1,2),.2),None));self.setup_health(lambda p:next(vals));self.tick();self.assertFalse(self.calls)
    def test_health_does_not_crowd_out_other_categories(self):
        others=[self.drop(str(i),'health',(301+i,0,0)) for i in range(6)]+[self.drop('cash','cash',(500,0,0)),self.drop('ammo','ammo',(510,0,0))]
        self.setup_health(lambda p:(('flesh',1,2),.5),others);self.tick();self.assertEqual({c[0] for c in self.calls},{'health','cash','ammo'})
        self.tick();self.assertEqual(len(self.calls),4)
    def test_join_during_health_read(self):
        reads=[]
        def read(p):
            reads.append(p)
            if len(reads)==2:self.ok=False
            return ('flesh',1,2),.4
        self.setup_health(read);self.tick();self.assertFalse(self.calls);self.assertIsNone(self.lease.record)
    def test_body_change_during_health_read(self):
        reads=[]
        def read(p):
            reads.append(p)
            if len(reads)==2:self.actors[0].BodyData.path='/Game/Pickups/Mission/Body.Body'
            return ('flesh',1,2),.4
        self.setup_health(read);self.tick();self.assertFalse(self.calls)
    def test_stop_during_health_read(self):
        reads=[]
        def read(p):
            reads.append(p)
            if len(reads)==2:self.lease.stop('manual')
            return ('flesh',1,2),.4
        self.setup_health(read);self.tick();self.assertFalse(self.calls)

class HealthNeedReaderTests(unittest.TestCase):
    def setUp(self):
        self.h=HealthPulse();self.h.setUp();self.addCleanup(self.h.doCleanups)
        from bl4_custom_foundation.loot_vacuum import flesh_need_reader
        self.h.p.Class._path_name=lambda:'/Script/OakGame.OakCharacter'
        self.h.p._path_name=lambda:'/Game/Test.Pawn'
        self.reader=flesh_need_reader(self.h.b.f.sdk)
    def test_flesh_not_shield(self):
        key,ratio=self.reader(self.h.p);self.assertEqual(key[0],self.h.hp._name);self.assertEqual(ratio,.5);self.assertFalse(self.h.calls)
    def test_healing_disabled(self):
        self.h.disabled._values['Value']=1
        with self.assertRaises(ValueError):self.reader(self.h.p)
    def test_ambiguous_flesh(self):
        self.h.p.HealthState.HealthTypeStates.append(self.h.flesh)
        with self.assertRaises(ValueError):self.reader(self.h.p)
    def test_dead(self):
        self.h.p.HealthState.bCurrentlyDead=True
        with self.assertRaises(ValueError):self.reader(self.h.p)
    def test_missing_handle(self):
        del self.h.b.f.sdk.unreal.FGameDataHandle
        with self.assertRaises(AttributeError):self.reader(self.h.p)
