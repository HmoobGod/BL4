import unittest
from unittest.mock import patch
from test_combat_r13 import Combat, Node, objdesc
from test_r3_persistent import Persistent

class WeaponWorkload(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        global w
        w=self.c.m.Controller.resolve.__globals__["weapon_rates"]
    def test_active_selection_one_slot_scan(self):
        with patch.object(w,'slot_entries',wraps=w.slot_entries) as scan:
            self.assertIs(w.active_weapon(self.c.p),self.c.w)
            self.assertEqual(scan.call_count,1)
    def test_active_monitor_two_fresh_slot_scans(self):
        self.c.activate('reload',2.)
        with patch.object(w,'slot_entries',wraps=w.slot_entries) as scan:
            self.c.m.monitor_tick();self.assertEqual(scan.call_count,2)
            self.c.m.monitor_tick();self.assertEqual(scan.call_count,4)
        self.assertEqual(self.c.reload.Value,1.5)
    def test_slot_descriptor_single_traversal_and_duplicate_rejection(self):
        t=self.c.slot_type; original=t._properties;calls=[]
        t._properties=lambda:(calls.append(1),original())[1]
        w.slot_entries(self.c.p);self.assertEqual(len(calls),1)
        t._properties=lambda:original()+[objdesc('Weapon','Weapon')]
        with self.assertRaises(ValueError):w.active_weapon(self.c.p)
    def test_new_pending_and_owner_observed_on_next_call(self):
        self.assertIs(w.active_weapon(self.c.p),self.c.w)
        slot=self.c.p.ActiveWeapons.Slots[0];slot.ClientPredictedPendingWeapon=self.c.w
        with self.assertRaises(ValueError):w.active_weapon(self.c.p)
        slot.ClientPredictedPendingWeapon=None;self.c.w.Owner=Node()
        with self.assertRaises(ValueError):w.active_weapon(self.c.p)
    def test_nonlocal_animation_skips_automation_fault_scan(self):
        p=Persistent();p.setUp();self.addCleanup(p.doCleanups)
        p.configure(walk_speed=2.);p.tick();p.m.ground_tick(p.anim)
        self.assertIn('walk_speed',p.m._controller.records)
        with patch.object(p.m,'automation_fault',wraps=p.m.automation_fault) as fault:
            p.m.ground_tick(Node());self.assertEqual(fault.call_count,0)
            p.m.ground_tick(p.anim);self.assertEqual(fault.call_count,1)
