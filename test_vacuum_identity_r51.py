"""Native-shaped reflected gear identity regression, no live game access."""
from test_vacuum_r26 import Continuous
from test_combat_r13 import Node, typ, desc


def uint(name):return type('ZUInt32Property',(),{'Name':name,'ArrayDim':1})()


def native_type(name,*props):
    t=typ(name,*props);t._path_name=lambda:'/Script/GbxGame.'+name;return t


class GearIdentity(Continuous):
    def gear(self,name,instance,quantity=1):
        a=self.drop(name,'gear',(400,0,0))
        dt=native_type('GbxItemData',uint('InstanceId'))
        st=native_type('GbxItemState',uint('Quantity'))
        it=native_type('GbxItem',desc('data',dt),desc('State',st))
        a.item=Node(_type=it,data=Node(_type=dt,InstanceId=instance),State=Node(_type=st,Quantity=quantity))
        a.Class._properties=lambda:[desc('item',it)]
        return a
    def test_positive_reflected_id(self):
        self.assertEqual(self.v.native_gear_identity(self.gear('gear',42)),(42,1))
    def test_duplicate_live_candidates_skipped(self):
        self.actors=[self.gear('a',10),self.gear('b',10),self.gear('c',20)]
        self.start(('gear',));self.tick();self.assertEqual([c[0] for c in self.calls],['c'])
    def test_replacement_actor_same_id_not_relocated(self):
        self.actors=[self.gear('a',10)];self.start(('gear',));self.tick()
        self.actors=[self.gear('replacement',10),self.gear('distinct',11)];self.tick()
        self.assertEqual([c[0] for c in self.calls],['a','distinct'])
    def test_native_refusal_consumes_id(self):
        self.actors=[self.gear('a',10)];self.move=lambda *args:self.calls.append(args) or False
        self.start(('gear',));self.tick();self.actors=[self.gear('b',10)];self.tick();self.assertEqual(len(self.calls),1)
    def test_zero_and_unexposed_keep_old_behavior(self):
        self.actors=[self.gear('zero',0),self.drop('unexposed','gear',(500,0,0))]
        self.start(('gear',));self.tick();self.assertEqual({c[0] for c in self.calls},{'zero','unexposed'});self.assertFalse(self.lease.gear_ids)
    def test_invalid_quantity_and_id(self):
        self.actors=[self.gear('zeroqty',1,0),self.gear('bool',True),self.gear('large',2**32),self.gear('negative',-1)]
        self.start(('gear',));self.tick();self.assertFalse(self.calls)
    def test_wrong_struct_path(self):
        a=self.gear('a',10);a.item.data._type._path_name=lambda:'/Script/Other.GbxItemData'
        self.actors=[a];self.start(('gear',));self.tick();self.assertFalse(self.calls)
    def test_wrong_wrapper_identity(self):
        a=self.gear('a',10);a.item.data._type=native_type('GbxItemData',uint('InstanceId'))
        self.actors=[a];self.start(('gear',));self.tick();self.assertFalse(self.calls)
    def test_late_id_change(self):
        a=self.gear('a',10);self.actors=[a];old=a.K2_GetActorRotation
        def changed():a.item.data.InstanceId=11;return old()
        changed.func=old.func;a.K2_GetActorRotation=changed
        self.start(('gear',));self.tick();self.assertFalse(self.calls)
    def test_late_quantity_change(self):
        a=self.gear('a',10);self.actors=[a];old=a.K2_GetActorRotation
        def changed():a.item.State.Quantity=2;return old()
        changed.func=old.func;a.K2_GetActorRotation=changed
        self.start(('gear',));self.tick();self.assertFalse(self.calls)
    def test_final_scope_read_changes_id(self):
        a=self.gear('a',10);self.actors=[a];self.start(('gear',));old=self.lease.resolve;calls=0
        def changed():
            nonlocal calls
            calls+=1
            if calls==4:a.item.data.InstanceId=99
            return old()
        self.lease.resolve=changed;self.tick();self.assertFalse(self.calls)
    def test_consumable_does_not_use_gear_identity(self):
        a=self.gear('gear',10);self.a.item=a.item;self.a.Class._properties=a.Class._properties
        self.actors=[self.a,a];self.start(('ammo','gear'));self.tick();self.assertEqual({c[0] for c in self.calls},{'a','gear'})
    def test_explicit_new_lease_clears_identity(self):
        self.actors=[self.gear('a',10)];self.start(('gear',));self.tick();self.lease.stop('test');self.assertTrue(self.lease.begin());self.actors=[self.gear('b',10)];self.tick();self.assertEqual([c[0] for c in self.calls],['a','b'])
