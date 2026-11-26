"""Native-shaped synthetic tests; no game or terrain simulation."""
from test_vacuum_r26 import Continuous
from test_movement_r29 import PersistentMovement
from test_combat_r13 import Node


class GearPlacement(Continuous):
    def test_more_than_eight_unique_targets(self):
        self.actors=[self.drop(str(i),'gear',(600+i,0,0)) for i in range(16)]
        self.start(('gear',))
        for _ in range(4): self.tick()
        pts=[c[1] for c in self.calls]
        self.assertEqual(len(pts),16)
        self.assertTrue(all(self.v.distance(a,b)>=100**2 for i,a in enumerate(pts) for b in pts[i+1:]))
        self.assertTrue(all(self.v.distance(p,(0,0,0))<=480**2+1e-6 for p in pts))
    def test_saturated_gear_does_not_starve_ammo(self):
        self.actors=[self.drop(str(i),'gear',(600+i,0,0)) for i in range(45)]
        self.start(('gear','ammo'))
        for _ in range(6):self.tick()
        self.tick(31)
        for _ in range(10):self.tick()
        self.assertIsNone(self.lease.gear_position((0,0,0),[]))
        self.actors.append(self.drop('ammo','ammo',(1000,0,0)))
        self.tick();self.assertEqual(self.calls[-1][0],'ammo')
        self.assertLessEqual(len(self.lease.gear_targets),36)
    def test_refused_target_is_reserved(self):
        self.actors=[self.drop(str(i),'gear',(600+i,0,0)) for i in range(2)]
        original=self.move
        self.move=lambda *a:original(*a) and False
        self.start(('gear',));self.tick()
        self.assertEqual(len(self.calls),2);self.assertEqual(self.lease.moved,0)
        self.assertNotEqual(self.calls[0][1],self.calls[1][1]);self.assertEqual(len(self.lease.gear_targets),2)
    def test_gear_avoids_vendor_at_destination(self):
        self.actors=[self.drop('gear','gear',(-600,0,0))]
        m=self.actor('vendor',(650,0,0));m.GetIOTDForPlayer=lambda pc:None;self.machines=[m]
        self.start(('gear',));self.tick();self.assertEqual(len(self.calls),1)
        self.assertGreater(self.v.distance(self.calls[0][1],m.pos),500**2)
    def test_late_vendor_near_target(self):
        self.actors=[self.drop('gear','gear',(-600,0,0))]
        self.start(('gear',));old=self.lease.make
        m=self.actor('vendor',(650,0,0));m.GetIOTDForPlayer=lambda pc:None
        def make(*a,**kw):
            self.machines.append(m);return old(*a,**kw)
        self.lease.make=make;self.tick();self.assertFalse(self.calls);self.assertFalse(self.lease.gear_targets)
    def test_move_anchor_ledger_retains_old_area(self):
        self.actors=[self.drop('gear','gear',(600,0,0))];self.start(('gear',));self.tick()
        first=self.calls[0][1];self.pawn.pos=(2000,0,0);self.actors.append(self.drop('new','gear',(2600,0,0)));self.tick()
        self.assertEqual(len(self.calls),2);self.assertEqual(len(self.lease.gear_targets),2)
        self.pawn.pos=(0,0,0);self.actors.append(self.drop('third','gear',(700,0,0)));self.tick()
        self.assertGreaterEqual(self.v.distance(self.calls[-1][1],first),100**2)
    def test_gear_ledger_clears_on_new_arm(self):
        self.actors=[self.drop('gear','gear',(600,0,0))];self.start(('gear',));self.tick();self.lease.stop('test');self.assertTrue(self.lease.begin());self.assertFalse(self.lease.gear_targets)


class Friction(PersistentMovement):
    def setUp(self):
        super().setUp();fields=list(self.comp.Class._properties())
        for name,val in (('GroundFriction',8.),('BrakingFrictionFactor',2.)):
            setattr(self.comp,name,val);fields.append(type('ZFloatProperty',(),{'Name':name,'ArrayDim':1})())
        self.comp.Class._properties=lambda:fields
    def friction(self):return self.comp.GroundFriction,self.comp.BrakingFrictionFactor
    def test_persistent_independent_restore(self):
        self.arm(ground_friction=.5,braking_friction=2.);self.tick();self.assertEqual(self.friction(),(4.,4.));self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
        self.m.apply({'ground_friction':1.,'braking_friction':.5});self.tick();self.assertEqual(self.friction(),(8.,1.));self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.friction(),(8.,2.))
    def test_default_off(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,'ground_friction':.5,'braking_friction':2.});self.tick();self.assertEqual(self.friction(),(8.,2.))
    def test_zero_waits_other_controls(self):
        self.comp.GroundFriction=0.;self.arm(ground_friction=.5,braking_friction=2.);self.tick();self.assertEqual(self.friction(),(0.,4.))
    def test_join_restores(self):
        self.arm(ground_friction=.5,braking_friction=2.);self.tick();self.p.f.players=2;self.tick();self.assertEqual(self.friction(),(8.,2.))
    def test_foreign_owner(self):
        self.comp.OakCharacterOwner=Node();self.p.configure(ground_friction=.5);self.tick();self.assertEqual(self.friction(),(8.,2.))
    def test_drift_not_overwritten(self):
        self.arm(ground_friction=.5);self.comp.GroundFriction=7.;self.tick();self.assertEqual(self.comp.GroundFriction,7.);self.assertTrue(self.m._controller.fault)
    def test_targeted_desired_matches_subset(self):
        self.m.apply({'persistent_ground_friction':True,'ground_friction':.5,'persistent_player_ammo_regen':True,'player_ammo_regen':2.})
        all_desired=self.m.raw_auto_desired();self.assertEqual(self.m.raw_auto_desired(self.m.AMMO_GROUP),{k:v for k,v in all_desired.items() if k in self.m.AMMO_GROUP})
    def test_targeted_desired_does_not_read_unrelated_flag(self):
        class Trap:
            @property
            def value(self):raise AssertionError('unrelated flag read')
        self.m.AUTO_OPTIONS['ground_friction']=Trap();self.assertFalse(self.m.ammo_selection_conflict(self.m.raw_auto_desired(self.m.AMMO_GROUP)))
