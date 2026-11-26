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
assert all(not isinstance(t,unittest.loader._FailedTest) for t in unique.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(unique.values()))
raise SystemExit(not result.wasSuccessful())
