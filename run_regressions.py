import unittest
loader = unittest.TestLoader()
suite = loader.loadTestsFromNames(['test_foundation','test_attribute_report','test_value_probe','test_batch','test_ui_update','test_hook_append','test_expansion','test_ground_speed','test_experimental','test_loader_metadata','test_r3_persistent','test_r3_hotfix','test_r4','test_r5','test_r6','test_r7','test_progression_inspect','test_r8_loot','test_r9_pearl','test_r10_gravity','test_sprint_r12.Sprint','test_combat_r13.Combat','test_recovery_r14.Recovery','test_recovery_r15.Swap','test_recovery_r15.Lease','test_combat_r16.WeaponTuning','test_native_recovery_binding.Binding','test_health_pulse_r17.HealthPulse','test_shield_pulse_r18.ShieldPulse','test_skill_pulse_r19.SkillPulseTests','test_reload_r20.ReloadTests','test_reload_r21.Continuous','test_inventory_r22.Inventory','test_reload_r23.FastReload','test_movement_r24.Movement','test_vacuum_r25.VacuumTests'])
def flatten(s):
    for t in s:
        if isinstance(t,unittest.TestSuite): yield from flatten(t)
        else: yield t
unique={t.id():t for t in flatten(suite)}
assert all(not isinstance(t,unittest.loader._FailedTest) for t in unique.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(unique.values()))
raise SystemExit(not result.wasSuccessful())
