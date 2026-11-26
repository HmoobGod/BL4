"""Synthetic reflection + existing F8 session tests, not native gameplay."""
import types
import unittest
import test_batch


class Node(types.SimpleNamespace):
    def _get_address(self): return id(self)
    def _path_name(self): return getattr(self,'Name','instance')


def desc(name, struct):
    return type('ZStructProperty', (), {'Name':name,'ArrayDim':1,'Struct':struct})()


def objdesc(name, classname):
    return type('ZObjectProperty', (), {'Name':name,'ArrayDim':1,'PropertyClass':Node(Name=classname)})()


def arraydesc(name, inner):
    return type('ZArrayProperty', (), {'Name':name,'ArrayDim':1,'Inner':inner})()


def typ(name, *props, parents=()):
    return Node(Name=name,_properties=lambda:list(props),_superfields=lambda:iter(parents))


def attr(value):
    a=test_batch.Attr(value); a._type.Name='GbxAttributeFloat'; a._type._get_address=lambda:id(a._type); return a


def struct(name, **fields):
    result=Node(**fields); result._type=typ(name,*(desc(k,v._type) for k,v in fields.items() if hasattr(v,'_type'))); return result


class Combat(unittest.TestCase):
    def setUp(self):
        self.b=test_batch.Batch();self.b.setUp();self.addCleanup(self.b.doCleanups)
        self.m=self.b.m;self.p=self.b.f.pawn
        self.fire=attr(8.);self.reload=attr(3.);self.minimum=attr(.5);self.health=attr(20.)
        h=self.p.HealthState; h.owner=self.p;h.RepairKitHealth=self.health;h._type=typ('OakCharacterHealthState',desc('RepairKitHealth',self.health._type))
        self.w=self.weapon(self.fire,self.reload,self.minimum)
        self.slot_type=typ('ActiveWeaponSlot',*(objdesc(n,'Weapon') for n in ('Weapon','PendingWeapon','ClientPredictedPendingWeapon')))
        active=Node(Slots=[self.slot(self.w)],_type=typ('OakActiveWeaponsState',arraydesc('Slots',desc('inner',self.slot_type))))
        self.p.ActiveWeapons=active; self.p.Class._properties=lambda:[desc('ActiveWeapons',active._type),desc('HealthState',h._type)]
    def slot(self,w):
        return Node(_type=self.slot_type,Weapon=w,PendingWeapon=None,ClientPredictedPendingWeapon=None)
    def weapon(self,fire,reload,minimum):
        w=Node(Name='weapon_instance',Class=typ('OakWeapon',arraydesc('behaviors',objdesc('inner','WeaponBehavior'))),Owner=self.p,bActorIsBeingDestroyed=False,CurrentUseModeIndex=0,CurrentState='Active')
        f=Node(Name='UM0_5B',Outer=w,firerate=fire,Class=typ('WeaponBehavior_OakFire',desc('firerate',fire._type),parents=(typ('WeaponBehavior_Fire'),)))
        r=Node(Name='UM0_6B',Outer=w,ReloadTime=reload,MinReloadTime=minimum,Class=typ('WeaponBehavior_StockReload',desc('ReloadTime',reload._type),desc('MinReloadTime',minimum._type)))
        w.behaviors=[f,r];return w
    def activate(self,k,v): self.b.activate(k,v)
    def vals(self,a):return (a.Value,a.BaseValue)
    def test_manual_only(self):
        for k in ('fire_rate','reload'): self.assertNotIn(k,self.m.AUTO_OPTIONS)
        self.assertFalse(self.m.AUTO_OPTIONS['repair_health'].value)
        self.assertEqual(self.fire.writes+self.reload.writes+self.health.writes,[])
    def test_fire_rate_cycle(self):
        self.activate('fire_rate',2.);self.assertEqual(self.vals(self.fire),(16.,16.));self.activate('fire_rate',3.);self.assertEqual(self.vals(self.fire),(24.,24.));self.activate('fire_rate',1.);self.assertEqual(self.vals(self.fire),(8.,8.))
    def test_reload_inverse(self):
        self.activate('reload',2.);self.assertEqual(self.vals(self.reload),(1.5,1.5));self.activate('reload',.5);self.assertEqual(self.vals(self.reload),(6.,6.));self.activate('reload',1.);self.assertEqual(self.vals(self.reload),(3.,3.))
    def test_reload_floor(self):
        self.minimum._values.update(Value=2.,BaseValue=2.);self.activate('reload',2.);self.assertEqual(self.reload.writes,[]);self.assertIn('native minimum',self.b.report())
    def test_repair_health_cycle(self):
        self.activate('repair_health',2.);self.assertEqual(self.vals(self.health),(40.,40.));self.activate('repair_health',1.);self.assertEqual(self.vals(self.health),(20.,20.))
    def test_both_rates_and_heal(self):
        for k in ('fire_rate','reload','repair_health'):self.activate(k,2.)
        self.assertEqual(len(self.m._controller.records),3);self.m.request_stop('test',immediate=True)
        self.assertEqual((self.vals(self.fire),self.vals(self.reload),self.vals(self.health)),((8.,8.),(3.,3.),(20.,20.)))
    def test_wrong_owner(self):
        self.w.Owner=Node();self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_wrong_behavior_outer(self):
        self.w.behaviors[0].Outer=Node();self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_no_fallback_mode(self):
        self.w.CurrentUseModeIndex=1;self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_mode_change_restores_original(self):
        self.activate('fire_rate',2.);self.w.CurrentUseModeIndex=1;self.m.monitor_tick();self.assertEqual(self.vals(self.fire),(8.,8.));self.assertFalse(self.m._controller.records)
    def test_switch_retained_weapon_restored(self):
        self.activate('fire_rate',2.);other=attr(4.);w=self.weapon(other,attr(2.),attr(.5));self.w.CurrentState='Inactive';self.p.ActiveWeapons.Slots.append(self.slot(w));self.m.monitor_tick();self.assertEqual(self.vals(self.fire),(8.,8.));self.assertEqual(other.writes,[])
    def test_removed_weapon_fault_no_replacement_write(self):
        self.activate('fire_rate',2.);other=attr(4.);self.p.ActiveWeapons.Slots=[self.slot(self.weapon(other,attr(2.),attr(.5)))];self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(other.writes,[])
    def test_ambiguous_active(self):
        self.p.ActiveWeapons.Slots.append(self.slot(self.weapon(attr(4.),attr(2.),attr(.5))));self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_ordnance_refused(self):
        self.w.Class.Name='HeavyWeaponGadget';self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_non_idle_activation(self):
        self.w.CurrentState='Reloading';self.activate('reload',2.);self.assertEqual(self.reload.writes,[])
    def test_heal_wrong_owner(self):
        self.p.HealthState.owner=Node();self.activate('repair_health',2.);self.assertEqual(self.health.writes,[])
    def test_heal_wrong_descriptor(self):
        self.p.HealthState._type=typ('OakCharacterHealthState');self.activate('repair_health',2.);self.assertEqual(self.health.writes,[])
    def test_pair_rollback(self):
        self.fire.raise_after='BaseValue';self.activate('fire_rate',2.);self.assertEqual(self.vals(self.fire),(8.,8.))
    def test_foreign_drift(self):
        self.activate('fire_rate',2.);self.fire._values['Value']=17.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.fire.Value,17.)
    def test_join_restores(self):
        self.activate('fire_rate',2.);self.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.vals(self.fire),(8.,8.))
    def test_pending_switch_restores_before_replacement(self):
        self.activate('fire_rate',2.);self.p.ActiveWeapons.Slots[0].PendingWeapon=self.weapon(attr(4.),attr(2.),attr(.5));self.m.monitor_tick();self.assertEqual(self.vals(self.fire),(8.,8.))
    def test_pending_activation_refused(self):
        self.p.ActiveWeapons.Slots[0].ClientPredictedPendingWeapon=self.w;self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_missing_slots_descriptor(self):
        self.p.ActiveWeapons._type._properties=lambda:[];self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_missing_behavior_descriptor(self):
        self.w.Class._properties=lambda:[];self.activate('fire_rate',2.);self.assertEqual(self.fire.writes,[])
    def test_reload_update_while_busy_restores(self):
        self.activate('reload',2.);self.w.CurrentState='Reloading';self.activate('reload',3.);self.assertEqual(self.vals(self.reload),(3.,3.))
