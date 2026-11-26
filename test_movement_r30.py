"""R30 native-shaped local energy costs and independent persistent combat/recovery fields."""
from test_movement_r29 import PersistentMovement
from test_combat_r13 import attr, desc, typ, Node

class EnergyControls(PersistentMovement):
    keys={'double_jump_cost':'VaultPowerCost_DoubleJump','dash_cost':'VaultPowerCost_Dash','glide_cost':'VaultPowerCost_Glide'}
    def setUp(self):
        super().setUp(); p=self.p.f.pawn
        self.attrs={k:attr(float(i*10)) for i,k in enumerate(self.keys,1)}
        props=list(self.comp.Class._properties())
        for k,n in self.keys.items():
            a=self.attrs[k];setattr(self.comp,n,a);props.append(desc(n,a._type))
        self.comp.Class._properties=lambda:props
        p._path_name=lambda:'LocalPawn';self.swap=attr(1.);p.WeaponSwapTimeScale=self.swap
        h=p.HealthState;h.owner=p;self.heal=attr(20.);h.RepairKitHealth=self.heal;h._type=typ('OakCharacterHealthState',desc('RepairKitHealth',self.heal._type))
        pp=list(getattr(p.Class,'_properties',lambda:[])());p.Class._properties=lambda:pp+[desc('WeaponSwapTimeScale',self.swap._type),desc('HealthState',h._type)]
    def costs(self):return tuple(a.Value for a in self.attrs.values())
    def test_default_off_costs_and_fields(self):
        self.m.apply({**dict.fromkeys(self.keys,.5),'swap_time':2.,'repair_health':2.,'persistent_master':True,'persistent_offline':True});self.tick();self.assertEqual(self.costs(),(10.,20.,30.));self.assertEqual((self.swap.Value,self.heal.Value),(1.,20.))
    def test_independent_costs_and_automation(self):
        self.arm(double_jump_cost=.5,dash_cost=.5,glide_cost=2.);self.tick();self.assertEqual(self.costs(),(5.,10.,60.));self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['double_jump_cost'],False);self.tick();self.assertEqual(self.costs(),(10.,10.,60.));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.costs(),(10.,20.,30.))
    def test_lower_bound_no_free_cost(self):
        self.arm(double_jump_cost=.1);self.tick();self.assertEqual(self.costs(),(1.,20.,30.));self.m.apply({'double_jump_cost':1.});self.tick();self.assertEqual(self.costs(),(10.,20.,30.))
    def test_owner_loss(self):
        self.comp.OakCharacterOwner=Node();self.p.configure(double_jump_cost=.5);self.tick();self.assertFalse(self.attrs['double_jump_cost'].writes)
    def test_zero_baseline_refused(self):
        self.attrs['double_jump_cost']._values.update(Value=0.,BaseValue=0.);self.p.configure(double_jump_cost=.5);self.tick();self.assertFalse(self.attrs['double_jump_cost'].writes)
    def test_join_restoration(self):
        self.arm(double_jump_cost=.5,dash_cost=.5,glide_cost=.5,swap_time=.5,repair_health=2.);self.tick();self.p.f.players=2;self.tick();self.assertEqual(self.costs(),(10.,20.,30.));self.assertEqual((self.swap.Value,self.heal.Value),(1.,20.));self.assertFalse(self.m._controller.records)
    def test_repair_swap_coexist(self):
        self.arm(swap_time=.5,repair_health=2.);self.tick();self.assertEqual((self.swap.Value,self.heal.Value),(.5,40.));self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'});self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual((self.swap.Value,self.heal.Value),(1.,20.))
    def test_health_owner_refused(self):
        self.p.f.pawn.HealthState.owner=Node();self.p.configure(repair_health=2.);self.tick();self.assertFalse(self.heal.writes)
    def test_cost_drift_fault(self):
        self.arm(double_jump_cost=.5);self.attrs['double_jump_cost']._values['Value']=7.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.costs()[0],7.);self.assertFalse(self.m._automation_leases)
