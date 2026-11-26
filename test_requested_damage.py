"""Equipped ordinary gun damage: mocked reflected instance, not live hit evidence."""
import unittest
from test_combat_r13 import Combat, attr, desc, Node
from test_combat_r31 import PersistentFire

def add_damage(f, value=100.):
    a=attr(value); f.damage=a
    old=list(f.Class._properties()); f.Class._properties=lambda:old+[desc('damage',a._type)]
    return a

class Damage(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.w=self.c.w;self.a=add_damage(self.w.behaviors[0]);self.p=self.c.p
        self.old=attr(1.);self.p.DamageCauserData=Node(DamageDealtMultiplier=self.old)
    def apply(self,v):self.c.activate('damage',v)
    def test_manual_cycle(self):
        for v,e in ((2.,200.),(.5,50.),(5.,500.),(1.,100.)):
            self.apply(v);self.assertEqual((self.a.Value,self.a.BaseValue),(e,e))
        self.assertFalse(self.old.writes)
    def test_default_off(self):self.assertFalse(self.m.AUTO_OPTIONS['damage'].value);self.assertFalse(self.a.writes)
    def test_missing_damage_no_old_fallback(self):
        del self.w.behaviors[0].damage;self.apply(2.);self.assertFalse(self.old.writes);self.assertFalse(self.a.writes)
    def test_no_stock_reload(self):self.w.behaviors.pop();self.apply(2.);self.assertFalse(self.a.writes)
    def test_foreign_outer(self):self.w.behaviors[0].Outer=Node();self.apply(2.);self.assertFalse(self.a.writes)
    def test_busy(self):self.w.CurrentState='Firing';self.apply(2.);self.assertFalse(self.a.writes)
    def test_wrong_mode(self):self.w.CurrentUseModeIndex=1;self.apply(2.);self.assertFalse(self.a.writes)
    def test_unequal_baseline(self):self.a._values['Value']=120.;self.apply(2.);self.assertFalse(self.a.writes)
    def test_ambiguous_fire(self):
        f=self.c.weapon(attr(5.),attr(2.),attr(.5)).behaviors[0];f.Outer=self.w;self.w.behaviors.append(f);self.apply(2.);self.assertFalse(self.a.writes)
    def test_partial_rollback(self):self.a.raise_after='BaseValue';self.apply(2.);self.assertEqual((self.a.Value,self.a.BaseValue),(100.,100.))
    def test_join_restore(self):self.apply(2.);self.c.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.a.Value,100.)
    def test_drift(self):self.apply(2.);self.a._values['Value']=201.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.a.Value,201.)

class PersistentDamage(unittest.TestCase):
    def setUp(self):
        self.c=PersistentFire();self.c.setUp();self.addCleanup(self.c.doCleanups);self.m=self.c.m;self.a=add_damage(self.c.fire)
    def test_combined(self):
        self.c.arm(damage=2.,fire_rate=1.5,jump=1.5);self.assertEqual(self.a.Value,200.);self.assertEqual(self.c.fire.firerate.Value,12.);self.c.r.empty();self.assertEqual(self.c.r.calls,[(0,0)]);self.assertIsNotNone(self.c.v.record)
        self.m.set_auto_setting(self.m.auto_master,False);self.c.tick();self.assertEqual(self.a.Value,100.)
    def test_swap(self):
        self.c.arm(damage=2.);w=self.c.r.c.weapon(attr(5.),attr(2.),attr(.5));other=add_damage(w.behaviors[0],70.);self.c.w.CurrentState='Inactive';self.c.r.p.ActiveWeapons.Slots.append(self.c.r.c.slot(w));self.c.tick(5);self.assertEqual(self.a.Value,100.);self.assertEqual(other.Value,140.)
    def test_busy_update_wait(self):
        self.c.arm(damage=2.);self.c.w.CurrentState='Firing';self.m.apply({'damage':3.});self.c.tick(2);self.assertEqual(self.a.Value,200.);self.c.w.CurrentState='Active';self.c.tick(2);self.assertEqual(self.a.Value,300.)
    def test_unsupported_wait(self):
        self.c.w.Class.Name='HeavyWeaponGadget';self.c.arm(damage=2.,jump=1.5);self.assertFalse(self.a.writes);self.assertIn('jump',self.m._controller.records);self.assertFalse(self.m._auto_blocked)
