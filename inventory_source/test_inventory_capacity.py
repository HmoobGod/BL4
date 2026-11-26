import unittest
from types import SimpleNamespace as N
from inventory_capacity import CONFIRM, CapacityFault, readback


def typed(name, **kw):
    return N(_type=N(Name=name), **kw)


def owner(value=70, base=16, count=12):
    field = typed('GbxAttributeInteger', Value=value, BaseValue=base)
    bag = typed('GbxItemContainer', MaxSize=field, ProfileId=0)
    slots = typed('GbxItemSlotsContainer', items=[object() for _ in range(count)])
    ps = N(Class=N(Name='OakPlayerState'), BackpackContainer=bag, BackpackItems=slots)
    return ps, field, slots


class Tests(unittest.TestCase):
    def test_backpack(self):
        ps, f, slots = owner()
        self.assertEqual(readback('backpack', CONFIRM, lambda: ps), (70, 71, 70))
        self.assertEqual((f.Value, f.BaseValue, len(slots.items)), (70, 16, 12))

    def test_bank(self):
        ps, f, slots = owner(100, 25)
        ps.BankContainer, ps.BankItems = ps.BackpackContainer, slots
        self.assertEqual(readback('bank', CONFIRM, lambda: ps), (100, 101, 100))
        self.assertEqual(f.BaseValue, 25)

    def test_bad_admission(self):
        for kind, confirm in [('lost_loot', CONFIRM), ('backpack', 'wrong')]:
            with self.subTest(kind=kind, confirm=confirm), self.assertRaises(CapacityFault):
                readback(kind, confirm, lambda: self.fail('context reached'))

    def test_bad_samples(self):
        for value, base, count in [(70,16,0),(70,16,71),(70,71,12),(True,1,1),(10000,16,1)]:
            ps, f, slots = owner(value,base,count)
            with self.subTest(value=value,base=base,count=count), self.assertRaises(CapacityFault):
                readback('backpack', CONFIRM, lambda: ps)
            self.assertEqual(f.Value,value)

    def test_wrong_class_and_struct(self):
        for mutate in [lambda ps: setattr(ps.Class,'Name','Other'),
                       lambda ps: setattr(ps.BackpackContainer._type,'Name','Other'),
                       lambda ps: setattr(ps.BackpackItems._type,'Name','Other'),
                       lambda ps: setattr(ps.BackpackContainer.MaxSize._type,'Name','Other')]:
            ps,f,_=owner();mutate(ps)
            with self.assertRaises(CapacityFault): readback('backpack',CONFIRM,lambda:ps)
            self.assertEqual(f.Value,70)

    def test_foreign_drift_not_overwritten(self):
        ps,f,_=owner();calls=0
        def ctx():
            nonlocal calls
            calls+=1
            if calls==3: f.Value=80
            return ps
        with self.assertRaises(CapacityFault): readback('backpack',CONFIRM,ctx)
        self.assertEqual(f.Value,80)

    def test_context_loss_no_stale_restore(self):
        ps,f,_=owner();calls=0
        def ctx():
            nonlocal calls
            calls+=1
            if calls>=3: raise CapacityFault('lost owner')
            return ps
        with self.assertRaises(CapacityFault): readback('backpack',CONFIRM,ctx)
        self.assertEqual(f.Value,71)

    def test_slot_change_no_unsafe_restore(self):
        ps,f,slots=owner();calls=0
        def ctx():
            nonlocal calls
            calls+=1
            if calls==3: slots.items.append(object())
            return ps
        with self.assertRaises(CapacityFault): readback('backpack',CONFIRM,ctx)
        self.assertEqual(f.Value,71)

    def test_setter_throws_after_write_restores(self):
        ps,f,_=owner()
        class Field:
            _type=N(Name='GbxAttributeInteger'); BaseValue=16; value=70
            @property
            def Value(self): return self.value
            @Value.setter
            def Value(self,v):
                self.value=v
                if v==71: raise RuntimeError('partial setter')
        field=Field();ps.BackpackContainer.MaxSize=field
        with self.assertRaises(RuntimeError): readback('backpack',CONFIRM,lambda:ps)
        self.assertEqual(field.Value,70)

if __name__=='__main__': unittest.main()
