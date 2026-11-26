"""v0.6.0 source-backed expansion tests using the existing mocked SDK."""
import types
import unittest
import test_batch

class Expansion(unittest.TestCase):
    def setUp(self):
        self.b = test_batch.Batch(); self.b.setUp(); self.addCleanup(self.b.doCleanups)
        self.m = self.b.m; self.p = self.b.f.pawn; self.r = self.b.f.state.RarityState
        A = test_batch.Attr
        self.p.DamageCauserData = types.SimpleNamespace(DamageDealtMultiplier=A(1.))
        self.p.DamageState = types.SimpleNamespace(DamageTakenMultiplier=A(1.), HealingReceivedMultiplier=A(1.))
        for n in ('ShockModifier','CorrosiveModifier','CryoModifier','RadiationModifier'):
            setattr(self.p.ElementalDamageModifiers,n,A(1.))
        self.p.HealthState.RepairKitDuration = A(8.)
        self.r.RareModifier = A(1.); self.r.VeryRareModifier = A(1.)
        self.r.CommonModifier = A(1.); self.r.UncommonModifier = A(1.); self.r.PearlescentModifier = A(1.)
        self.b.jump.MaxWalkSpeed = 600.
        self.b.jump.GravityScale = 1.
        self.b.jump.MinAnalogWalkSpeed = 0.
        self.b.jump.bIsSprinting = False
        self.anim=types.SimpleNamespace(_get_address=lambda:987654)
        self.p.Mesh=types.SimpleNamespace(GetAnimInstance=lambda:self.anim)
        self.b.f.pc.OakCharacter=self.p
        self.b.f.sdk.hooks.Type.POST='anim_post'
        self.b.jump.Class._properties = lambda: [type('ZFloatProperty',(),{'Name':n,'ArrayDim':1})() for n in ('JumpZVelocity','MaxWalkSpeed','MinAnalogWalkSpeed','GravityScale')]
    def pair_cycle(self, key, attr, base=1., multiplier=2.):
        self.b.activate(key,multiplier); self.assertIn(key,self.m._controller.records)
        self.assertEqual((attr.Value,attr.BaseValue),(base*multiplier,)*2)
        self.b.activate(key,3.); self.assertEqual((attr.Value,attr.BaseValue),(base*3,)*2)
        self.b.activate(key,1.); self.assertEqual((attr.Value,attr.BaseValue),(base,)*2)
    def test_outgoing_hold(self): self.b.activate('damage',2.); self.assertEqual(self.p.DamageCauserData.DamageDealtMultiplier.writes,[]); self.assertIn('feature HOLD',self.b.report())
    def test_incoming_experimental(self): self.pair_cycle('damage_taken',self.p.DamageState.DamageTakenMultiplier, multiplier=.5)
    def test_shock_experimental(self): self.pair_cycle('shock_damage',self.p.ElementalDamageModifiers.ShockModifier)
    def test_corrosive_experimental(self): self.pair_cycle('corrosive_damage',self.p.ElementalDamageModifiers.CorrosiveModifier)
    def test_cryo_experimental(self): self.pair_cycle('cryo_damage',self.p.ElementalDamageModifiers.CryoModifier)
    def test_radiation_experimental(self): self.pair_cycle('radiation_damage',self.p.ElementalDamageModifiers.RadiationModifier)
    def test_healing(self): self.pair_cycle('healing_received',self.p.DamageState.HealingReceivedMultiplier)
    def test_duration(self): self.pair_cycle('repair_duration',self.p.HealthState.RepairKitDuration,8.,.5)
    def ground(self, value):
        self.b.activate('walk_speed', value)
        self.b.hooks[(self.m._GROUND_PATH, 'anim_post', self.m._GROUND_ID)](self.anim)
    def test_walk(self):
        self.ground(2.); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1080.); self.assertEqual(self.b.jump.MaxWalkSpeed,600.)
        self.ground(3.); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1620.)
        self.ground(1.); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
    def test_rare(self):
        self.b.activate('rare_weight',2.); self.assertEqual(self.r.RareModifier.Value,2.); self.assertEqual(self.r.RareModifier.BaseValue,1.)
        self.b.activate('rare_weight',3.); self.assertEqual(self.r.RareModifier.Value,3.)
        self.b.activate('rare_weight',1.); self.assertEqual(self.r.RareModifier.Value,1.)
    def test_epic(self):
        self.b.activate('epic_weight',2.); self.assertEqual(self.r.VeryRareModifier.Value,2.)
        self.b.activate('epic_weight',1.); self.assertEqual(self.r.VeryRareModifier.Value,1.)
    def test_epic_alias(self):
        self.r.EpicModifier=self.r.VeryRareModifier; del self.r.VeryRareModifier
        self.b.activate('epic_weight',2.); self.assertEqual(self.r.EpicModifier.Value,2.)
    def test_epic_ambiguous(self):
        self.r.EpicModifier=test_batch.Attr(1.); self.b.activate('epic_weight',2.)
        self.assertEqual(self.r.VeryRareModifier.writes,[]); self.assertEqual(self.r.EpicModifier.writes,[])
    def test_alias_collision(self):
        self.r.VeryRareModifier=self.r.RareModifier; self.b.activate('rare_weight',2.); self.b.activate('epic_weight',3.)
        self.assertEqual(self.r.RareModifier.Value,1.); self.assertIn('field already owned',self.b.report())
    def test_all_available(self):
        from bl4_custom_foundation.gameplay_fields import FEATURES
        from bl4_custom_foundation.session_control import DAMAGE_HOLD
        from test_combat_r13 import attr,typ,desc
        comp=self.p.CharacterMovement
        comp.DashSpeed=attr(1200.);comp.GlidingSpeed=attr(800.)
        original=comp.Class._properties()
        comp.Class=typ('OakCharacterMovementComponent',*original,desc('DashSpeed',comp.DashSpeed._type),desc('GlidingSpeed',comp.GlidingSpeed._type))
        comp._path_name=lambda:'OwnedMovement';comp.OakCharacterOwner=self.p
        fields=list(comp.Class._properties())
        for n in ('VaultPowerCost_DoubleJump','VaultPowerCost_Dash','VaultPowerCost_Glide'):
            a=attr(10.);setattr(comp,n,a);fields.append(desc(n,a._type))
        comp.Class._properties=lambda:fields
        self.p._path_name=lambda:'LocalPawn';self.p.WeaponSwapTimeScale=attr(1.)
        h=self.p.HealthState;h.owner=self.p;h.RepairKitHealth=attr(20.);h._type=typ('OakCharacterHealthState',desc('RepairKitHealth',h.RepairKitHealth._type))
        prior=list(getattr(self.p.Class,'_properties',lambda:[])());self.p.Class._properties=lambda:prior+[desc('WeaponSwapTimeScale',self.p.WeaponSwapTimeScale._type),desc('HealthState',h._type)]
        for k in FEATURES:
            if k in DAMAGE_HOLD or k in self.m.MANUAL_ONLY or k in self.m.FIRE_KEYS: continue
            if k == 'walk_speed': self.ground(2.)
            else: self.b.activate(k,1.2 if k == 'gravity' else 2.)
        self.assertEqual(len(self.m._controller.records),25)
        self.m.request_stop('test',immediate=True); self.assertFalse(self.m._controller.records); self.assertFalse(self.m._controller.fault)
        self.assertEqual(self.r.RareModifier.Value,1.); self.assertEqual(self.b.jump.MaxWalkSpeed,600.)
    def test_new_loot_on_pawn_change(self):
        self.b.activate('rare_weight',2.); self.b.activate('epic_weight',3.)
        self.b.f.pc.Pawn=types.SimpleNamespace(Class=self.p.Class,_get_address=lambda:99999)
        self.m.monitor_tick(); self.assertEqual(self.r.RareModifier.Value,1.); self.assertEqual(self.r.VeryRareModifier.Value,1.)
        self.assertFalse(self.m._controller.records)
    def test_zero_rarity_hold(self):
        self.r.RareModifier._values['Value']=0.; self.b.activate('rare_weight',2.)
        self.assertEqual(self.r.RareModifier.writes,[])
    def test_new_fraction_cycle(self):
        self.b.activate('epic_weight',2.5); self.assertEqual(self.r.VeryRareModifier.Value,2.5)
        self.b.activate('epic_weight',1.); self.assertEqual(self.r.VeryRareModifier.Value,1.)
    def test_new_pair_partial_restore(self):
        a=self.p.DamageState.HealingReceivedMultiplier; a.reject='BaseValue'; self.b.activate('healing_received',2.)
        self.assertEqual((a.Value,a.BaseValue),(1.,1.)); self.assertFalse(self.m._controller.fault)
    def test_new_coop_blocked(self):
        self.b.f.players=2; self.b.activate('damage',2.); self.assertEqual(self.p.DamageCauserData.DamageDealtMultiplier.writes,[])
