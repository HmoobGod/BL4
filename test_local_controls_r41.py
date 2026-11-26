"""Synthetic local native attribute and grenade persistence checks."""
from test_gadget_rates_r40 import GadgetCooldown
from test_movement_r29 import PersistentMovement
from test_combat_r13 import attr, desc, Node
from test_automation_r27 import Lane
from types import SimpleNamespace as N

class PersistentGrenade(GadgetCooldown):
    def setUp(self):
        super().setUp();self.now=100.;self.m.time=N(monotonic=lambda:self.now);self.b.f.solo=True
        self.m.close_menu();self.b.gui.finish_close();self.m.make_automation_lane=lambda kind,session:Lane(kind,self.m)
    def tick(self,n=1):
        for _ in range(n):self.now+=.3;self.m._auto_next=0.;self.m.monitor_tick()
    def arm(self,**settings):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**settings});self.tick(4)
    def test_default_off(self):
        self.arm(grenade_cooldown=2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_swap_and_restore(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.,persistent_jump=True,jump=2.);self.assertEqual(self.vals(),(6.,6.))
        self.current=self.make();self.current.CooldownTime._values.update(Value=18.,BaseValue=18.);self.tick(2);self.assertEqual(self.vals(),(12.,12.));self.assertEqual(self.current.CooldownTime.Value,9.);self.assertIn('jump',self.m._controller.records)
        self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.current.CooldownTime.Value,18.)
    def test_busy_initial_wait(self):
        self.g.bIsUsing=True;self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.,persistent_jump=True,jump=2.);self.assertFalse(self.g.CooldownTime.writes);self.assertIn('jump',self.m._controller.records)
        self.g.bIsUsing=False;self.tick();self.assertEqual(self.vals(),(6.,6.))
    def test_busy_update_wait(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.);self.g.bIsUsing=True;self.m.apply({'grenade_cooldown':3.});self.tick();self.assertEqual(self.vals(),(6.,6.));self.g.bIsUsing=False;self.tick();self.assertEqual(self.vals(),(4.,4.))
    def test_missing_wait_and_return(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.);self.current=None;self.tick();self.assertEqual(self.vals(),(12.,12.));self.current=self.make();self.tick();self.assertEqual(self.current.CooldownTime.Value,6.)
    def test_lost_owner_fault(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.,persistent_jump=True,jump=2.);self.current=self.make();self.g.OwningCharacter=Node();self.tick();self.assertTrue(self.m._controller.fault);self.assertFalse(self.current.CooldownTime.writes);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_foreign_drift_no_rebind(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.);self.current=self.make();self.g.CooldownTime._values['Value']=7.;self.tick();self.assertTrue(self.m._controller.fault);self.assertFalse(self.current.CooldownTime.writes)
    def test_join_restores_persistent(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.);self.b.f.players=2;self.tick();self.assertEqual(self.vals(),(12.,12.))
    def test_automation_compatible(self):
        self.arm(persistent_grenade_cooldown=True,grenade_cooldown=2.,persistent_automation_reload=True,persistent_automation_vacuum=True,vacuum_pref_ammo=True);self.assertEqual(set(self.m._automation_leases),{'reload','vacuum'});self.assertEqual(self.vals(),(6.,6.))

class LocalMovement(PersistentMovement):
    keys={'ladder_ascend':'MaxLadderAscendSpeed','ladder_descend':'MaxLadderDescendSpeed','slam_height':'GroundSlamHeightScalar'}
    def setUp(self):
        super().setUp();self.extra={k:attr(10.) for k in self.keys};fields=list(self.comp.Class._properties())
        for k,n in self.keys.items():
            a=self.extra[k];setattr(self.comp,n,a);fields.append(desc(n,a._type))
        self.comp.Class._properties=lambda:fields
    def vals_extra(self):return tuple((a.Value,a.BaseValue) for a in self.extra.values())
    def test_defaults(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**dict.fromkeys(self.keys,2.)});self.tick();self.assertEqual(self.vals_extra(),((10.,10.),)*3)
    def test_independent_and_restore(self):
        self.arm(ladder_ascend=2.,ladder_descend=.5,slam_height=1.5);self.assertEqual(self.vals_extra(),((20.,20.),(5.,5.),(15.,15.)));self.assertEqual(set(self.m._automation_leases),{'reload','vacuum'});self.m.apply({'ladder_ascend':1.,'ladder_descend':3.});self.tick();self.assertEqual(self.vals_extra(),((10.,10.),(30.,30.),(15.,15.)));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.vals_extra(),((10.,10.),)*3)
    def test_missing_field_wait(self):
        del self.comp.MaxLadderAscendSpeed;self.arm(ladder_ascend=2.,ladder_descend=2.);self.assertFalse(self.extra['ladder_ascend'].writes);self.assertEqual(self.extra['ladder_descend'].Value,20.);self.assertFalse(self.m._auto_blocked)
    def test_owner_refused(self):
        self.comp.OakCharacterOwner=Node();self.p.configure(ladder_ascend=2.);self.tick();self.assertFalse(self.extra['ladder_ascend'].writes)
    def test_slam_bound(self):
        from bl4_custom_foundation.gameplay_fields import target_values
        with self.assertRaises(ValueError):target_values('slam_height',(10.,),((1,'Value','ZFloatProperty'),),3.)
    def test_join_restores(self):
        self.arm(**dict.fromkeys(self.keys,2.));self.p.f.players=2;self.tick();self.assertEqual(self.vals_extra(),((10.,10.),)*3)

class PlayerAmmo(GadgetCooldown):
    def setUp(self):
        super().setUp();self.a=attr(2.);self.p.ammoregenrate=self.a;self.p._path_name=lambda:'LocalPawn';prior=list(getattr(self.p.Class,'_properties',lambda:[])());self.p.Class._properties=lambda:prior+[desc('ammoregenrate',self.a._type)]
    def test_manual_positive_cycle(self):
        self.assertIn('player_ammo_regen',self.m.AUTO_OPTIONS);self.b.activate('player_ammo_regen',3.);self.assertEqual((self.a.Value,self.a.BaseValue),(6.,6.));self.b.activate('player_ammo_regen',1.);self.assertEqual((self.a.Value,self.a.BaseValue),(2.,2.))
    def test_zero_not_enabled(self):
        self.a._values.update(Value=0.,BaseValue=0.);self.b.activate('player_ammo_regen',2.);self.assertFalse(self.a.writes)
    def test_unequal_refused(self):
        self.a._values['Value']=3.;self.b.activate('player_ammo_regen',2.);self.assertFalse(self.a.writes)
    def test_no_overlap_weapon_rate(self):
        self.b.activate('player_ammo_regen',2.);self.assertFalse(self.m._controller.activate('ammo_regen_rate',2.));self.assertEqual(self.a.Value,4.);self.assertIn('player_ammo_regen',self.m._controller.records)
    def test_join_restores_ammo(self):
        self.b.activate('player_ammo_regen',2.);self.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.a.Value,2.)
