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

    def arm_fire_group(self):
        from test_combat_r13 import attr,desc
        from test_requested_damage import add_damage
        f=self.c.w.behaviors[0]
        self.damage=add_damage(f)
        self.spread=attr(4.);self.recoil=attr(2.)
        f.spread=self.spread;f.RecoilScale=self.recoil
        old=f.Class._properties()
        f.Class._properties=lambda:old+[desc('spread',self.spread._type),desc('RecoilScale',self.recoil._type)]
        for key,v in [('damage',2.),('fire_rate',2.),('weapon_spread',.5),('weapon_recoil',.5)]:
            self.c.activate(key,v)
        self.assertEqual(set(self.c.m._controller.records),set(w.FIRE_KEYS))
        self.attrs=(self.damage,self.c.fire,self.spread,self.recoil)

    def test_four_fire_controls_two_slot_scans_no_writes(self):
        self.arm_fire_group()
        before=[list(a.writes) for a in self.attrs]
        with patch.object(w,'slot_entries',wraps=w.slot_entries) as scan:
            self.c.m.monitor_tick();self.assertEqual(scan.call_count,2)
            self.c.m.monitor_tick();self.assertEqual(scan.call_count,4)
        self.assertEqual(before,[a.writes for a in self.attrs])
        self.assertEqual([a.Value for a in self.attrs],[200.,16.,2.,1.])

    def test_four_fire_controls_two_behavior_observations(self):
        self.arm_fire_group()
        original=self.c.w.Class._properties;calls=[]
        self.c.w.Class._properties=lambda:(calls.append(1),original())[1]
        self.c.m.monitor_tick();self.assertEqual(len(calls),2)

    def test_fire_group_pending_restores_original(self):
        self.arm_fire_group();self.c.p.ActiveWeapons.Slots[0].PendingWeapon=self.c.w
        self.c.m.monitor_tick()
        self.assertEqual([a.Value for a in self.attrs],[100.,8.,4.,2.])
        self.assertFalse(self.c.m._controller.records)

    def test_fire_group_foreign_drift_not_overwritten(self):
        self.arm_fire_group();self.spread._values['Value']=3.
        self.c.m.monitor_tick()
        self.assertEqual([a.Value for a in self.attrs],[100.,8.,3.,2.])
        self.assertTrue(self.c.m._controller.fault)

    def test_fire_group_removed_weapon_never_writes_replacement(self):
        from test_combat_r13 import attr
        self.arm_fire_group();replacement=attr(9.)
        self.c.p.ActiveWeapons.Slots=[self.c.slot(self.c.weapon(replacement,attr(3.),attr(.5)))]
        self.c.m.monitor_tick()
        self.assertTrue(self.c.m._controller.fault);self.assertFalse(replacement.writes)

    def test_fire_group_detects_pending_between_brackets(self):
        self.arm_fire_group();original=w.active_weapon;calls=[]
        def active(pawn):
            calls.append(1)
            if len(calls)==2:self.c.p.ActiveWeapons.Slots[0].PendingWeapon=self.c.w
            return original(pawn)
        with patch.object(w,'active_weapon',side_effect=active):self.c.m.monitor_tick()
        self.assertEqual([a.Value for a in self.attrs],[100.,8.,4.,2.])
        self.assertFalse(self.c.m._controller.records)

    def test_fire_group_restore_never_uses_group_observation(self):
        self.arm_fire_group()
        with patch.object(w,'observe_fire_group',side_effect=AssertionError('restore used group')) as grouped:
            self.c.m.request_stop('test',immediate=True)
            grouped.assert_not_called()
        self.assertEqual([a.Value for a in self.attrs],[100.,8.,4.,2.])

    def test_fire_group_join_restores_all(self):
        self.arm_fire_group();self.c.b.f.players=2
        self.c.m.monitor_tick()
        self.assertEqual([a.Value for a in self.attrs],[100.,8.,4.,2.])
        self.assertFalse(self.c.m._controller.records)
