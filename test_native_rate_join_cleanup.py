"""Regression for removal of an original local native rate on eligibility loss."""
import unittest
from test_native_resource_rates import NativeRateTests

class NativeRateJoinCleanup(unittest.TestCase):
    def setUp(self):
        self.c=NativeRateTests(); self.c.setUp(); self.addCleanup(self.c.doCleanups)

    def health_lane(self, missing=False):
        c=self.c
        if missing: lane=c.missing_health_trial()
        else:
            c.resolve=c.local_health(); lane=c.trial()
            lane.cleanup_key=lambda k:c.R.original_pool_identity('health',k)
        self.assertTrue(lane.begin(),c.msg); c.tick(lane)
        self.assertEqual(lane.phase,'active',c.msg)
        return lane

    def test_health_original_cleanup_on_join(self):
        c=self.c; lane=self.health_lane(); c.allowed=False
        c.tick(lane,permit=False); c.tick(lane,permit=False)
        self.assertEqual([x[0] for x in c.native],['add','remove'])
        self.assertEqual(lane.phase,'done',c.msg); self.assertEqual(c.rate,0.)

    def test_missing_health_original_cleanup_on_join(self):
        c=self.c; lane=self.health_lane(True); c.allowed=False
        c.tick(lane,permit=False); c.tick(lane,permit=False)
        self.assertEqual([x[0] for x in c.native],['add','remove'])
        self.assertEqual(lane.phase,'done',c.msg); self.assertEqual(c.peer_rate,.012)

    def test_replacement_not_cleanup_target(self):
        c=self.c; lane=self.health_lane(); c.allowed=False
        from test_combat_r13 import Node
        c.world=Node(); c.tick(lane,permit=False)
        self.assertTrue(lane.fault); self.assertEqual([x[0] for x in c.native],['add'])

    def test_ineligible_no_new_modifier(self):
        c=self.c; c.resolve=c.local_health(); lane=c.trial(); c.allowed=False
        self.assertFalse(lane.begin()); self.assertFalse(c.native)

    def test_loss_before_dispatch_no_new_modifier(self):
        c=self.c; c.resolve=c.local_health(); lane=c.trial()
        self.assertTrue(lane.begin()); c.allowed=False; c.tick(lane,permit=False)
        self.assertFalse(c.native)

    def test_authority_unavailable_refuses_cleanup(self):
        c=self.c; lane=self.health_lane()
        def lost(): raise ValueError('local authoritative controller unavailable')
        lane.resolve.original=lost
        c.allowed=False; c.tick(lane,permit=False)
        self.assertTrue(lane.fault); self.assertEqual([x[0] for x in c.native],['add'])

    def test_uncertain_add_on_join_still_faults(self):
        c=self.c; c.resolve=c.local_health(); lane=c.trial()
        lane.cleanup_key=lambda k:c.R.original_pool_identity('health',k)
        old=c.binding.calls['AddModifierToGbxAttribute']
        def add(*a):
            c.echo=False
            result=old(*a); c.allowed=False; return result
        c.binding.calls['AddModifierToGbxAttribute']=add
        self.assertTrue(lane.begin()); c.tick(lane); c.tick(lane,permit=False)
        self.assertTrue(lane.fault); self.assertEqual([x[0] for x in c.native],['add','remove']); self.assertEqual(c.rate,0.)

    def test_restored_lane_does_not_rearm_when_solo_returns(self):
        c=self.c; lane=self.health_lane(); c.allowed=False
        c.tick(lane,permit=False); c.tick(lane,permit=False)
        self.assertEqual(lane.phase,'done'); c.allowed=True
        for _ in range(5): c.tick(lane)
        self.assertEqual([x[0] for x in c.native],['add','remove'])
