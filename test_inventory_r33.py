import unittest
from types import SimpleNamespace as N
from test_inventory_r22 import Inventory
from test_automation_r27 import Lane

class PersistentCapacity(unittest.TestCase):
    def setUp(self):
        self.i=Inventory();self.i.setUp();self.addCleanup(self.i.doCleanups)
        self.m=self.i.m;self.now=100.;self.m.time=N(monotonic=lambda:self.now)
        self.lanes={}
        def factory(k,s):
            l=Lane(k,self.m);self.lanes[k]=l;return l
        self.m.make_automation_lane=factory
    def tick(self,n=1):
        for _ in range(n):self.now+=.3;self.m.monitor_tick()
    def arm(self,**v):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**v,**{'persistent_'+k:True for k in v}});self.tick(5)
    def test_independent_and_restore(self):
        self.arm(backpack_capacity=250,bank_capacity=500)
        self.assertEqual((self.i.back.Value,self.i.bank.Value),(250,500))
        self.m.apply({'backpack_capacity':300});self.tick();self.assertEqual((self.i.back.Value,self.i.bank.Value),(300,500))
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['backpack_capacity'],False);self.tick();self.assertEqual((self.i.back.Value,self.i.bank.Value),(40,500))
        self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual((self.i.back.Value,self.i.bank.Value),(40,100))
    def test_default_off(self):
        self.m.apply({'backpack_capacity':250,'bank_capacity':500});self.arm();self.assertEqual(self.i.back.writes+self.i.bank.writes,[])
    def test_invalid_capacity_does_not_block_other(self):
        self.arm(backpack_capacity=20,bank_capacity=500);self.assertEqual((self.i.back.Value,self.i.bank.Value),(40,500));self.assertFalse(self.m._auto_blocked)
    def test_overfull_disable_holds_until_unloaded(self):
        self.arm(backpack_capacity=250,bank_capacity=500);self.i.ps.BackpackItems.items.extend([object()]*50)
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['backpack_capacity'],False);self.tick();self.assertEqual((self.i.back.Value,self.i.bank.Value),(250,100));self.assertFalse(self.m._controller.fault);self.assertIn('Capacity restore waiting',self.m._auto_blocked)
        del self.i.ps.BackpackItems.items[10:];self.tick();self.assertEqual(self.i.back.Value,40);self.assertFalse(self.m._controller.records)
    def test_overfull_master_off(self):
        self.arm(backpack_capacity=250);self.i.ps.BackpackItems.items.extend([object()]*50);self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.i.back.Value,250);self.assertFalse(self.m._controller.fault)
        del self.i.ps.BackpackItems.items[10:];self.tick();self.assertEqual(self.i.back.Value,40)
    def test_overfull_reenable_does_not_cancel(self):
        self.arm(backpack_capacity=250);self.i.ps.BackpackItems.items.extend([object()]*50);self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.m.set_auto_setting(self.m.auto_master,True);self.tick();self.assertTrue(self.m._controller.records['backpack_capacity']['overfull_warning']);self.assertFalse(self.m.auto_allowed())
    def test_invalid_update_preserves_active(self):
        self.arm(backpack_capacity=250);self.i.ps.BackpackItems.items.extend([object()]*100);self.m.apply({'backpack_capacity':100});self.tick();self.assertEqual(self.i.back.Value,250);self.assertFalse(self.m._auto_blocked)
    def test_sdu_change_fault(self):
        self.arm(bank_capacity=500);self.i.bank._values['BaseValue']=110;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.i.bank.writes,[('Value',500)])
    def test_join_restore(self):
        self.arm(bank_capacity=500);self.i.b.f.players=2;self.tick();self.assertEqual(self.i.bank.Value,100)
    def test_automation_coexists_and_stops_on_overfull_restore(self):
        self.arm(backpack_capacity=250);self.m.apply({'persistent_automation_vacuum':True,'persistent_automation_reload':True,'vacuum_pref_ammo':True});self.tick(4);self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
        self.i.ps.BackpackItems.items.extend([object()]*50);self.m.set_auto_setting(self.m.AUTO_OPTIONS['backpack_capacity'],False);self.tick();self.assertFalse(self.m._automation_leases);self.assertEqual(self.i.back.Value,250)
