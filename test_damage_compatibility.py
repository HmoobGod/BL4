"""Ordinary gun damage compatibility; synthetic SDK reflection only."""
import unittest
from test_combat_r13 import Combat, Node, typ, desc, objdesc, attr
from test_requested_damage import add_damage

RELOAD='/Script/GbxWeapon.WeaponBehavior_Reload'
HEAT='/Script/GbxWeapon.WeaponBehavior_Heat'
USE='/Script/GbxWeapon.WeaponBehavior_Use'

class DamageCompatibility(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.w=self.c.w;self.fire=self.w.behaviors[0];self.a=add_damage(self.fire)
        self.stock=self.w.behaviors.pop()
        self.w.Class._path_name=lambda:'/Script/OakGame.OakWeapon'
        base=typ('WeaponBehavior_Fire');base._path_name=lambda:'/Script/GbxWeapon.WeaponBehavior_Fire'
        self.fire.Class._superfields=lambda:iter((base,))
    def reload(self, name=RELOAD, parents=()):
        r,m=attr(3.),attr(.5)
        return Node(Name='UM0_reload',Outer=self.w,ReloadTime=r,MinReloadTime=m,Class=typ(name,desc('ReloadTime',r._type),desc('MinReloadTime',m._type),parents=parents))
    def heat(self):
        return Node(Name='UM0_heat',Outer=self.w,UseBehavior=self.fire,Class=typ(HEAT,objdesc('UseBehavior',USE)))
    def apply(self,v=2.):self.c.activate('damage',v)
    def test_native_reload_damage_restore(self):
        r=self.reload();self.w.behaviors.append(r);self.apply();self.assertEqual(self.a.Value,200.);self.apply(1.);self.assertEqual(self.a.Value,100.);self.assertFalse(r.ReloadTime.writes)
    def test_native_derived_reload_damage(self):
        self.w.behaviors.append(self.reload('/Script/OakGame.TestNativeReload',parents=(typ(RELOAD),)));self.apply();self.assertEqual(self.a.Value,200.)
    def test_heat_damage_restore(self):
        self.w.behaviors.append(self.heat());self.apply();self.assertEqual(self.a.Value,200.);self.apply(1.);self.assertEqual(self.a.Value,100.)
    def test_heat_join_restores(self):
        self.w.behaviors.append(self.heat());self.apply();self.c.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.a.Value,100.)
    def test_foreign_heat(self):
        h=self.heat();h.Outer=Node();self.w.behaviors.append(h);self.apply();self.assertFalse(self.a.writes)
    def test_heat_wrong_use(self):
        h=self.heat();h.UseBehavior=Node();self.w.behaviors.append(h);self.apply();self.assertFalse(self.a.writes)
    def test_heat_wrong_mode(self):
        h=self.heat();h.Name='UM1_heat';self.w.behaviors.append(h);self.apply();self.assertFalse(self.a.writes)
    def test_ambiguous_alternate(self):
        self.w.behaviors.extend([self.reload(),self.heat()]);self.apply();self.assertFalse(self.a.writes)
    def test_native_reload_invalid_floor(self):
        r=self.reload();r.MinReloadTime._values.update(Value=4.,BaseValue=4.);self.w.behaviors.append(r);self.apply();self.assertFalse(self.a.writes)
    def test_fake_reload(self):
        self.w.behaviors.append(self.reload('/Game/FakeReload',parents=(typ(RELOAD),)));self.apply();self.assertFalse(self.a.writes)
    def test_gadget_still_refused(self):
        self.w.Class.Name='HeavyWeaponGadget';self.w.behaviors.append(self.heat());self.apply();self.assertFalse(self.a.writes)
    def test_stock_priority(self):
        self.w.behaviors.extend([self.stock,self.heat()]);self.apply();self.assertEqual(self.a.Value,200.)
    def test_ambiguous_stock_no_fallback(self):
        self.w.behaviors.extend([self.stock,self.stock,self.heat()]);self.apply();self.assertFalse(self.a.writes)
    def test_replaced_witness_restores(self):
        self.w.behaviors.append(self.heat());self.apply();self.w.behaviors[-1]=self.heat();self.m.monitor_tick();self.assertEqual(self.a.Value,100.);self.assertFalse(self.m._controller.records)
    def test_missing_witness_restores(self):
        self.w.behaviors.append(self.heat());self.apply();self.w.behaviors.pop();self.m.monitor_tick();self.assertEqual(self.a.Value,100.)
    def test_wrong_native_weapon_path(self):
        self.w.Class._path_name=lambda:'/Game/OakWeapon';self.w.behaviors.append(self.heat());self.apply();self.assertFalse(self.a.writes)
    def test_wrong_native_fire_path(self):
        self.fire.Class._superfields=lambda:iter((typ('WeaponBehavior_Fire'),));self.w.behaviors.append(self.heat());self.apply();self.assertFalse(self.a.writes)
    def test_alternate_partial_write_rolls_back(self):
        self.w.behaviors.append(self.heat());self.a.raise_after='BaseValue';self.apply();self.assertEqual((self.a.Value,self.a.BaseValue),(100.,100.))
    def test_alternate_foreign_drift_not_overwritten(self):
        self.w.behaviors.append(self.heat());self.apply();self.a._values['Value']=201.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.a.Value,201.)
    def test_other_reload_control_unchanged(self):
        r=self.reload();self.w.behaviors.append(r);self.c.activate('reload',2.);self.assertFalse(r.ReloadTime.writes)


from test_combat_r31 import PersistentFire

class PersistentDamageCompatibility(unittest.TestCase):
    def setUp(self):
        self.c=PersistentFire();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.w=self.c.w;self.a=add_damage(self.c.fire)
        self.add_heat(self.w)
    def add_heat(self,w):
        f=w.behaviors[0];w.behaviors.pop();w.Class._path_name=lambda:'/Script/OakGame.OakWeapon'
        base=typ('WeaponBehavior_Fire');base._path_name=lambda:'/Script/GbxWeapon.WeaponBehavior_Fire';f.Class._superfields=lambda:iter((base,))
        w.behaviors.append(Node(Name='UM0_heat',Outer=w,UseBehavior=f,Class=typ(HEAT,objdesc('UseBehavior',USE))))
    def test_persistent_heat_live_slider_and_off(self):
        self.c.arm(damage=2.,jump=1.5);self.assertEqual(self.a.Value,200.);self.m.apply({'damage':3.});self.c.tick(3);self.assertEqual(self.a.Value,300.);self.m.set_auto_setting(self.m.auto_master,False);self.c.tick();self.assertEqual(self.a.Value,100.)
    def test_persistent_swap_to_stock(self):
        self.c.arm(damage=2.,jump=1.5);self.w.CurrentState='Inactive';new=self.c.r.c.weapon(attr(5.),attr(3.),attr(.5));other=add_damage(new.behaviors[0],70.);self.c.r.p.ActiveWeapons.Slots.append(self.c.r.c.slot(new));self.c.tick(5);self.assertEqual(self.a.Value,100.);self.assertEqual(other.Value,140.);self.assertIn('jump',self.m._controller.records)
