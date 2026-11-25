import unittest
loader = unittest.TestLoader()
suite = loader.loadTestsFromNames(['test_foundation','test_attribute_report','test_value_probe','test_batch','test_ui_update','test_hook_append','test_expansion','test_ground_speed','test_experimental','test_loader_metadata','test_r3_persistent','test_r3_hotfix','test_r4','test_r5','test_r6','test_r7','test_progression_inspect','test_r8_loot','test_r9_pearl'])
def flatten(s):
    for t in s:
        if isinstance(t,unittest.TestSuite): yield from flatten(t)
        else: yield t
unique={t.id():t for t in flatten(suite)}
assert all(not isinstance(t,unittest.loader._FailedTest) for t in unique.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(unique.values()))
raise SystemExit(not result.wasSuccessful())
