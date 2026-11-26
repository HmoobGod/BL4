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
assert all(not isinstance(t,unittest.loader._FailedTest) for t in unique.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(unique.values()))
raise SystemExit(not result.wasSuccessful())
