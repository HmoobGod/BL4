"""Synthetic inventory tests; not native save or game evidence."""
import sys
import unittest
from test_combat_r13 import Node, typ, desc, arraydesc, struct
import test_batch


class Inventory(unittest.TestCase):
    def setUp(self):
        self.b=test_batch.Batch();self.b.setUp();self.addCleanup(self.b.doCleanups)
        self.m=self.b.m;self.pc=self.b.f.pc;self.pawn=self.b.f.pawn
        self.ps=Node(Name='playerstate',Owner=self.pc)
        self.back=self.add_container('Backpack',40,10)
        self.bank=self.add_container('Bank',100,20)
        self.ps.Class=typ('OakPlayerState',*(desc(k,v._type) for k,v in vars(self.ps).items() if hasattr(v,'_type')))
        self.pc.PlayerState=self.pawn.PlayerState=self.ps
    def add_container(self,prefix,capacity,count):
        a=test_batch.Attr(capacity)
        a._type=typ('GbxAttributeInteger',*(type('ZIntProperty',(),{'Name':n,'ArrayDim':1})() for n in ('Value','BaseValue')))
        c=struct('GbxItemContainer',MaxSize=a)
        slots=Node(_type=typ('GbxItemSlotsContainer',arraydesc('items',desc('inner',typ('GbxItemContainerSlot')))),items=[object() for _ in range(count)])
        setattr(self.ps,prefix+'Container',c);setattr(self.ps,prefix+'Items',slots)
        return a
    def activate(self,k,v):self.b.activate(k,v)
    def test_no_startup(self):
        self.assertEqual(self.back.writes+self.bank.writes,[])
        self.assertFalse(self.m.AUTO_OPTIONS['bank_capacity'].value)
        self.assertFalse(self.m.AUTO_OPTIONS['backpack_capacity'].value)
    def test_independent(self):
        self.activate('backpack_capacity',250);self.assertEqual(self.back.Value,250);self.assertEqual(self.bank.writes,[])
        self.activate('bank_capacity',500);self.assertEqual((self.back.Value,self.bank.Value),(250,500))
        self.activate('backpack_capacity',300);self.assertEqual((self.back.Value,self.bank.Value),(300,500))
        self.assertEqual((self.back.BaseValue,self.bank.BaseValue),(40,100))
    def test_restore_both(self):
        self.activate('backpack_capacity',250);self.activate('bank_capacity',500)
        self.m.request_stop('test',immediate=True)
        self.assertEqual((self.back.Value,self.bank.Value),(40,100));self.assertFalse(self.m._controller.records)
    def test_restore_one(self):
        self.activate('backpack_capacity',250);self.activate('bank_capacity',500);self.activate('backpack_capacity',1)
        self.assertEqual((self.back.Value,self.bank.Value),(40,500))
    def test_no_reduction_below_original(self):
        self.activate('backpack_capacity',20);self.assertEqual(self.back.writes,[])
    def test_initial_overfull(self):
        self.ps.BackpackItems.items.extend([object()]*50);self.activate('backpack_capacity',250);self.assertEqual(self.back.writes,[])
    def test_restore_overfull_never_shrinks(self):
        self.activate('backpack_capacity',250);self.ps.BackpackItems.items.extend([object()]*50)
        self.activate('backpack_capacity',1);self.assertEqual(self.back.Value,250);self.assertFalse(self.m._controller.fault)
        self.assertTrue(self.m._controller.records['backpack_capacity']['overfull_warning'])
        del self.ps.BackpackItems.items[10:];self.activate('backpack_capacity',1);self.assertEqual(self.back.Value,40)
    def test_global_restore_waits_for_unload(self):
        self.activate('backpack_capacity',250);self.ps.BackpackItems.items.extend([object()]*50)
        self.m.request_stop('test',immediate=True);self.assertEqual(self.back.Value,250);self.assertFalse(self.m._controller.fault)
        del self.ps.BackpackItems.items[10:];self.m.monitor_tick();self.assertEqual(self.back.Value,40)
    def test_update_below_count(self):
        self.activate('backpack_capacity',250);self.ps.BackpackItems.items.extend([object()]*100)
        self.activate('backpack_capacity',100);self.assertEqual(self.back.Value,250)
    def test_sdu_change(self):
        self.activate('bank_capacity',500);self.bank._values['BaseValue']=110;self.m.monitor_tick()
        self.assertTrue(self.m._controller.fault);self.assertEqual(self.bank.writes,[('Value',500)])
    def test_wrong_owner(self):
        self.ps.Owner=Node();self.activate('bank_capacity',500);self.assertEqual(self.bank.writes,[])
    def test_wrong_pawn(self):
        self.pawn.PlayerState=Node();self.activate('bank_capacity',500);self.assertEqual(self.bank.writes,[])
    def test_alias(self):
        self.ps.BankContainer=self.ps.BackpackContainer;self.activate('backpack_capacity',250);self.assertEqual(self.back.writes,[])
    def test_foreign_value(self):
        self.activate('bank_capacity',500);self.bank._values['Value']=333;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.bank.Value,333)
    def test_join(self):
        self.activate('bank_capacity',500);self.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.bank.Value,100)
    def test_fractional(self):
        self.activate('bank_capacity',200.5);self.assertEqual(self.bank.writes,[])
    def test_cap(self):
        self.activate('bank_capacity',1001);self.assertEqual(self.bank.writes,[])
    def test_missing_descriptor(self):
        self.ps.BankItems._type._properties=lambda:[];self.activate('bank_capacity',500);self.assertEqual(self.bank.writes,[])
    def test_replacement_player_state(self):
        self.activate('bank_capacity',500);self.pc.PlayerState=self.pawn.PlayerState=Node();self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.bank.writes,[('Value',500)])
    def test_conflict(self):
        sys.modules['BiggerBackpackAndBank']=Node();self.addCleanup(sys.modules.pop,'BiggerBackpackAndBank',None)
        self.activate('bank_capacity',500);self.assertEqual(self.bank.writes,[])
    def test_post_write_error_rollback(self):
        self.bank.raise_after='Value';self.activate('bank_capacity',500);self.assertEqual((self.bank.Value,self.bank.BaseValue),(100,100))
    def test_integer_normalize(self):
        o=next(x for x in self.m.PREVIEW if x.identifier=='bank_capacity');self.assertEqual(self.m.normalize(o,250.3),250)
