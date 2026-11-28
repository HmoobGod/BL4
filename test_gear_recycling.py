"""Synthetic gear placement lifetime: no native pickup or collision proof."""
from test_vacuum_r26 import Continuous

class GearRecycling(Continuous):
    def start_gear(self):
        self.actors=[self.drop('original','gear',(600,0,0))]
        self.start(('gear','ammo'))
        dead=set();self.dead=dead
        self.lease.weak=lambda obj:lambda:None if self.v.identity(obj) in dead else obj
        self.tick();self.original=self.actors[0];self.first=self.calls[0][1]
        self.cell=self.v.gear_cell(self.first)
    def retire(self):
        self.dead.add(self.v.identity(self.original));self.actors.remove(self.original)
    def new(self,name='new'):
        a=self.drop(name,'gear',(700,0,0));self.actors.append(a);return a
    def test_reuse_after_collection(self):
        self.start_gear();self.retire();self.new();self.tick()
        self.assertEqual(self.calls[-1][1],self.first);self.assertEqual(len(self.lease.attempted),2)
        self.assertEqual(len(self.lease.gear_targets),1)
    def test_live_absent_retains(self):
        self.start_gear();self.actors.remove(self.original);self.new();self.tick()
        self.assertNotEqual(self.calls[-1][1],self.first);self.assertIn(self.cell,self.lease.gear_targets)
    def test_dead_still_enumerated_retains(self):
        self.start_gear();self.dead.add(self.v.identity(self.original));self.new();self.tick()
        self.assertNotEqual(self.calls[-1][1],self.first)
    def test_occupied_retains(self):
        self.start_gear();self.retire();self.actors.append(self.drop('near','gear',self.first));self.new();self.tick()
        self.assertNotEqual(self.calls[-1][1],self.first);self.assertIn(self.cell,self.lease.gear_targets)
    def test_unknown_location_retains(self):
        self.start_gear();self.retire();a=self.new();a.K2_GetActorLocation=lambda:None
        self.actors.append(self.drop('ammo','ammo',(600,0,0)));self.tick()
        self.assertEqual(self.calls[-1][0],'ammo');self.assertIn(self.cell,self.lease.gear_targets)
    def test_late_occupant_blocks_recycled_target(self):
        self.start_gear();self.retire();a=self.new();old=a.K2_GetActorRotation
        def arrive():
            self.actors.append(self.drop('near','gear',self.first));return old()
        arrive.func=old.func;a.K2_GetActorRotation=arrive;self.tick()
        self.assertEqual(len(self.calls),1);self.assertNotIn(self.v.identity(a),self.lease.attempted)
    def test_dedup_preserved(self):
        self.start_gear();self.retire();self.new();self.tick();self.actors.append(self.original)
        self.dead.clear();self.tick();self.assertEqual(len(self.calls),2)
    def test_reset_clears_recycled_cells(self):
        self.start_gear();self.retire();self.tick();self.assertIn(self.cell,self.lease.recycled_cells)
        self.lease.stop('test');self.assertTrue(self.lease.begin());self.assertFalse(self.lease.recycled_cells);self.assertFalse(self.lease.gear_receipts)
    def test_wrong_level_occupant_does_not_block(self):
        self.start_gear();self.retire();a=self.drop('near','gear',self.first);a.Outer=self.drop('other','gear',(0,0,0)).Outer
        from test_vacuum_r25 import Obj
        a.Outer=Obj('another',Class=Obj('/Script/Engine.Level'));self.actors.append(a);self.new();self.tick();self.assertEqual(self.calls[-1][1],self.first)
    def test_duplicate_scan_refuses_reclaim(self):
        self.start_gear();self.retire();a=self.new();self.actors.append(a);self.tick();self.assertIn(self.cell,self.lease.gear_targets)
