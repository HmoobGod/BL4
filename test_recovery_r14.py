"""Synthetic existing-rate experiments, no game process or native calls."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class Recovery(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.m=self.c.m; self.p=self.c.p; self.w=self.c.w
        self.rate=attr(2.);self.delay=attr(4.);self.life=attr(2.);self.cap=attr(8.);self.percent=attr(.1)
        self.pool=Node(Name='UM0_7B',Outer=self.w,RegenRate=self.rate,ConsumeRegenDelay=self.delay,Class=typ('WeaponBehavior_AmmoPool',desc('RegenRate',self.rate._type),desc('ConsumeRegenDelay',self.delay._type)))
        self.w.behaviors.append(self.pool)
        self.damage=Node(owner=self.p,lifestealrate=self.life,lifestealratecap=self.cap,lifestealpercent=self.percent,_type=typ('OakDamageState',desc('lifestealrate',self.life._type),desc('lifestealratecap',self.cap._type),desc('lifestealpercent',self.percent._type)))
        self.p.DamageState=self.damage
        prior=self.p.Class._properties(); self.p.Class._properties=lambda:prior+[desc('DamageState',self.damage._type)]
    def activate(self,k,v):self.c.activate(k,v)
    def vals(self,a):return self.c.vals(a)
    def zero(self,a):a._values.update(Value=0.,BaseValue=0.)
    def test_rate(self):
        self.activate('ammo_regen_rate',2.);self.assertEqual(self.vals(self.rate),(4.,4.));self.activate('ammo_regen_rate',1.);self.assertEqual(self.vals(self.rate),(2.,2.))
    def test_delay(self):
        self.activate('ammo_regen_delay',2.);self.assertEqual(self.vals(self.delay),(2.,2.));self.activate('ammo_regen_delay',1.);self.assertEqual(self.vals(self.delay),(4.,4.))
    def test_life(self):
        self.activate('lifesteal_rate',3.);self.assertEqual(self.vals(self.life),(6.,6.));self.activate('lifesteal_rate',1.);self.assertEqual(self.vals(self.life),(2.,2.));self.assertEqual(self.cap.writes+self.percent.writes,[])
    def test_no_new_regen(self):
        self.zero(self.rate);self.activate('ammo_regen_rate',2.);self.assertEqual(self.rate.writes,[])
    def test_no_delay_if_no_regen(self):
        self.zero(self.rate);self.activate('ammo_regen_delay',2.);self.assertEqual(self.delay.writes,[])
    def test_no_ordnance(self):
        self.w.Class.Name='HeavyWeaponGadget';self.activate('ammo_regen_rate',2.);self.assertEqual(self.rate.writes,[])
    def test_no_reload_behavior(self):
        self.w.behaviors.pop(1);self.activate('ammo_regen_rate',2.);self.assertEqual(self.rate.writes,[])
    def test_wrong_mode(self):
        self.pool.Name='UM1_7B';self.activate('ammo_regen_rate',2.);self.assertEqual(self.rate.writes,[])
    def test_life_cap(self):
        self.cap._values.update(Value=3.,BaseValue=3.);self.activate('lifesteal_rate',2.);self.assertEqual(self.life.writes,[])
    def test_life_zero_percent(self):
        self.zero(self.percent);self.activate('lifesteal_rate',2.);self.assertEqual(self.life.writes,[])
    def test_life_zero_rate(self):
        self.zero(self.life);self.activate('lifesteal_rate',2.);self.assertEqual(self.life.writes,[])
    def test_life_wrong_owner(self):
        self.damage.owner=Node();self.activate('lifesteal_rate',2.);self.assertEqual(self.life.writes,[])
    def test_life_cap_changes(self):
        self.activate('lifesteal_rate',2.);self.cap._values.update(Value=3.,BaseValue=3.);self.m.monitor_tick();self.assertEqual(self.vals(self.life),(2.,2.))
    def test_regen_lost_restores_delay(self):
        self.activate('ammo_regen_delay',2.);self.zero(self.rate);self.m.monitor_tick();self.assertEqual(self.vals(self.delay),(4.,4.))
    def test_mode_switch(self):
        self.activate('ammo_regen_rate',2.);self.w.CurrentUseModeIndex=1;self.m.monitor_tick();self.assertEqual(self.vals(self.rate),(2.,2.))
    def test_manual_only(self):
        for k in ('ammo_regen_rate','ammo_regen_delay','lifesteal_rate'):self.assertNotIn(k,self.m.AUTO_OPTIONS)
    def test_compatible(self):
        for k in ('ammo_regen_rate','ammo_regen_delay','lifesteal_rate','fire_rate'):self.activate(k,2.)
        self.assertEqual(len(self.m._controller.records),4);self.m.request_stop('test',immediate=True);self.assertEqual((self.vals(self.rate),self.vals(self.delay),self.vals(self.life)),((2.,2.),(4.,4.),(2.,2.)))
