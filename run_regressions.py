import unittest
loader = unittest.TestLoader()
suite = loader.loadTestsFromNames(['test_foundation','test_attribute_report','test_value_probe','test_batch','test_ui_update','test_hook_append','test_expansion','test_ground_speed','test_experimental','test_loader_metadata','test_r3_persistent','test_r3_hotfix','test_r4','test_r5','test_r6','test_r7','test_progression_inspect','test_r8_loot','test_r9_pearl','test_r10_gravity','test_sprint_r12.Sprint','test_combat_r13.Combat','test_recovery_r14.Recovery','test_recovery_r15.Swap','test_recovery_r15.Lease','test_combat_r16.WeaponTuning','test_native_recovery_binding.Binding','test_health_pulse_r17.HealthPulse','test_shield_pulse_r18.ShieldPulse','test_skill_pulse_r19.SkillPulseTests','test_reload_r20.ReloadTests','test_reload_r21.Continuous','test_inventory_r22.Inventory','test_reload_r23.FastReload','test_movement_r24.Movement','test_vacuum_r25.VacuumTests','test_automation_r27.Automation','test_automation_r27.SessionReload'])
def flatten(s):
    for t in s:
        if isinstance(t,unittest.TestSuite): yield from flatten(t)
        else: yield t
unique={t.id():t for t in flatten(suite)}
from test_vacuum_r26 import Continuous
for name in Continuous.__dict__:
    if name.startswith('test_'):
        t=Continuous(name);unique[t.id()]=t
from test_automation_r28 import SwapReload, LiveVacuum, Coexist
for cls in (SwapReload, LiveVacuum, Coexist):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_movement_r29 import PersistentMovement, ReloadRecovery
for cls in (PersistentMovement, ReloadRecovery):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_movement_r30 import EnergyControls
for name in EnergyControls.__dict__:
    if name.startswith('test_'):
        t=EnergyControls(name);unique[t.id()]=t
from test_combat_r31 import PersistentFire, ExternalReload
for cls in (PersistentFire, ExternalReload):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_combat_r32 import PersistentReload, LastReserve
for cls in (PersistentReload, LastReserve):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_inventory_r33 import PersistentCapacity
for name in PersistentCapacity.__dict__:
    if name.startswith("test_"):
        t=PersistentCapacity(name);unique[t.id()]=t
from test_recovery_r34 import ContinuousRecovery
for name in ContinuousRecovery.__dict__:
    if name.startswith('test_'):
        t=ContinuousRecovery(name);unique[t.id()]=t
from test_recovery_r35 import PersistentSkill, RecoveryRates
for cls in (PersistentSkill,RecoveryRates):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_movement_r36 import GlideHandling
for name in GlideHandling.__dict__:
    if name.startswith('test_'):
        t=GlideHandling(name);unique[t.id()]=t
from test_shield_rates_r37 import ShieldRates
for name in ShieldRates.__dict__:
    if name.startswith("test_"):
        t=ShieldRates(name);unique[t.id()]=t
from test_shield_rates_r38 import PersistentShield, RealRecoveryShield
for cls in (PersistentShield, RealRecoveryShield):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_performance_r39 import LateVacuum, ConflictIndex
for cls in (LateVacuum, ConflictIndex):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_gadget_rates_r40 import GadgetCooldown
for name in GadgetCooldown.__dict__:
    if name.startswith('test_'):
        t=GadgetCooldown(name);unique[t.id()]=t
from test_local_controls_r41 import PersistentGrenade, LocalMovement, PlayerAmmo
for cls in (PersistentGrenade, LocalMovement, PlayerAmmo):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_ammo_r42 import PersistentAmmo
for name in PersistentAmmo.__dict__:
    if name.startswith('test_'):
        t=PersistentAmmo(name);unique[t.id()]=t
from test_adaptive_skill_r43 import AdaptiveSkill
for name in AdaptiveSkill.__dict__:
    if name.startswith('test_'):
        t=AdaptiveSkill(name);unique[t.id()]=t
from test_r44_placement import GearPlacement,Friction
for cls in (GearPlacement,Friction):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_slide_r45 import SlideScale
for name in SlideScale.__dict__:
    if name.startswith('test_'):
        t=SlideScale(name);unique[t.id()]=t
from test_slide_timing_r46 import SlideTiming
for name in SlideTiming.__dict__:
    if name.startswith('test_'):
        t=SlideTiming(name);unique[t.id()]=t
from test_f8_focus_r47 import FocusRows
for name in FocusRows.__dict__:
    if name.startswith('test_'):
        t=FocusRows(name);unique[t.id()]=t
from test_skill_sets_r48 import ExternalSkillSets
for name in ExternalSkillSets.__dict__:
    if name.startswith('test_'):
        t=ExternalSkillSets(name);unique[t.id()]=t
from test_skill_follow_r49 import SkillFollow
for name in SkillFollow.__dict__:
    if name.startswith('test_'):
        t=SkillFollow(name);unique[t.id()]=t
from test_vacuum_r50 import HighGear
for name in HighGear.__dict__:
    if name.startswith("test_"):
        t=HighGear(name);unique[t.id()]=t
from test_vacuum_identity_r51 import GearIdentity
for name in GearIdentity.__dict__:
    if name.startswith('test_'):
        t=GearIdentity(name);unique[t.id()]=t
from test_double_jump_r52 import JumpVelocity
for name in JumpVelocity.__dict__:
    if name.startswith('test_'):
        t=JumpVelocity(name);unique[t.id()]=t
from test_jump_event_r53 import JumpEvent, Registration
for cls in (JumpEvent, Registration):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_lifesteal_r54 import LifeFraction
for name in LifeFraction.__dict__:
    if name.startswith('test_'):
        t=LifeFraction(name);unique[t.id()]=t
from test_overshield_r55 import Overshield
for name in Overshield.__dict__:
    if name.startswith('test_'):
        t=Overshield(name);unique[t.id()]=t
from test_vacuum_dlc_r56 import DlcGear
for name in DlcGear.__dict__:
    if name.startswith('test_'):
        t=DlcGear(name);unique[t.id()]=t
from test_health_overtime_r57 import NativeTimedHealth
for name in NativeTimedHealth.__dict__:
    if name.startswith('test_'):
        t=NativeTimedHealth(name);unique[t.id()]=t
from test_native_skill_r58 import NativeSkill
for name in NativeSkill.__dict__:
    if name.startswith('test_'):
        t=NativeSkill(name);unique[t.id()]=t
from test_f8_panels_r59 import ActionPanels
for name in ActionPanels.__dict__:
    if name.startswith('test_'):
        t=ActionPanels(name);unique[t.id()]=t
from test_crossfire_r60 import Crossfire
for name in Crossfire.__dict__:
    if name.startswith('test_'):
        t=Crossfire(name);unique[t.id()]=t
from test_vacuum_body_r61 import PickupBody
for name in PickupBody.__dict__:
    if name.startswith('test_'):
        t=PickupBody(name);unique[t.id()]=t
from test_native_regen_r62 import NativeRegenTest
for name in NativeRegenTest.__dict__:
    if name.startswith('test_'):
        t=NativeRegenTest(name);unique[t.id()]=t
from test_requested_damage import Damage, PersistentDamage
for cls in (Damage, PersistentDamage):
    for name in cls.__dict__:
        if name.startswith('test_'):
            t=cls(name);unique[t.id()]=t
from test_requested_named_cooldown import NamedCooldown
for name in NamedCooldown.__dict__:
    if name.startswith('test_'):
        t=NamedCooldown(name);unique[t.id()]=t
from test_requested_cooldown_follow import NamedFollow
for name in NamedFollow.__dict__:
    if name.startswith('test_'):
        t=NamedFollow(name);unique[t.id()]=t
from test_requested_reload_wait import ReloadWait
for name in ReloadWait.__dict__:
    if name.startswith('test_'):
        t=ReloadWait(name);unique[t.id()]=t
from test_gemini_luck_categories import LuckEvidence
for name in LuckEvidence.__dict__:
    if name.startswith('test_'):
        t=LuckEvidence(name);unique[t.id()]=t
from test_persistent_lifesteal import PersistentLife
for name in PersistentLife.__dict__:
    if name.startswith('test_'):
        t=PersistentLife(name);unique[t.id()]=t
from test_native_resource_rates import NativeRateTests
for name in NativeRateTests.__dict__:
    if name.startswith('test_'):
        t=NativeRateTests(name);unique[t.id()]=t
from test_blackboard_rewards import RewardTests
for name in RewardTests.__dict__:
    if name.startswith('test_'):
        t=RewardTests(name);unique[t.id()]=t
from test_activation_recovery import ActivationRecovery
for name in ActivationRecovery.__dict__:
    if name.startswith("test_"):
        t=ActivationRecovery(name);unique[t.id()]=t
from test_active_workload import ActiveWorkload
for name in ActiveWorkload.__dict__:
    if name.startswith("test_"):
        t=ActiveWorkload(name);unique[t.id()]=t
from test_weapon_workload import WeaponWorkload
for name in WeaponWorkload.__dict__:
    if name.startswith("test_"):
        t=WeaponWorkload(name);unique[t.id()]=t
from test_reload_fps import ReloadFPS
for name in ReloadFPS.__dict__:
    if name.startswith("test_"):
        t=ReloadFPS(name);unique[t.id()]=t
from test_handoff_recovery import HandoffRecovery, GroundRearm
for cls in (HandoffRecovery, GroundRearm):
    for name in cls.__dict__:
        if name.startswith("test_"):
            t=cls(name);unique[t.id()]=t
from test_reload_persistence import ReloadPersistence
for name in ReloadPersistence.__dict__:
    if name.startswith('test_'):
        t=ReloadPersistence(name);unique[t.id()]=t
from test_reload_window import ReloadEvent
for name in ReloadEvent.__dict__:
    if name.startswith('test_'):
        t=ReloadEvent(name);unique[t.id()]=t
from test_critical_damage import CriticalDamage
for name in CriticalDamage.__dict__:
    if name.startswith("test_"):
        t=CriticalDamage(name);unique[t.id()]=t
from test_f8_simple import SimpleF8
for name in SimpleF8.__dict__:
    if name.startswith('test_'):
        t=SimpleF8(name);unique[t.id()]=t
assert all(not isinstance(t,unittest.loader._FailedTest) for t in unique.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(unique.values()))
raise SystemExit(not result.wasSuccessful())
