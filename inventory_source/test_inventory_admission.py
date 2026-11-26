import sys
import threading
import time
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import inventory_admission as a
from inventory_capacity import CONFIRM


class Obj(N):
    _counter = 100
    def __init__(self, **kw):
        super().__init__(**kw)
        Obj._counter += 1
        self.addr = Obj._counter
    def _get_address(self): return self.addr


class Struct(Obj):
    def _find_prop(self, name): return self.props[name]


def prop(name, kind, **kw):
    return type(kind, (Obj,), {})(Name=name, ArrayDim=1, **kw)


def st(name, **props): return Struct(Name=name, props=props)


class UFunction(Obj):
    def _path_name(self): return a.PATH


class BoundFunction(N): pass


class WeakPointer:
    def __init__(self, obj): self.obj = obj
    def __call__(self): return self.obj


class Fixture:
    def __init__(self):
        at = st('GbxAttributeInteger', Value=prop('Value','ZIntProperty'),
                BaseValue=prop('BaseValue','ZIntProperty'))
        ct = st('GbxItemContainer', MaxSize=prop('MaxSize','ZStructProperty',Struct=at),
                ProfileId=prop('ProfileId','ZByteProperty'))
        ht = st('InventoryItemHandle', Handle=prop('Handle','ZIntProperty'))
        it = st('InventoryItem', Handle=prop('Handle','ZStructProperty',Struct=ht),
                EquipSlot=prop('EquipSlot','ZInt8Property'))
        slot = st('GbxItemContainerSlot', InventoryItem=prop('InventoryItem','ZStructProperty',Struct=it))
        slots = st('GbxItemSlotsContainer', items=prop('items','ZArrayProperty',
                   Inner=prop('Inner','ZStructProperty',Struct=slot)))
        psclass = st('OakPlayerState', BackpackContainer=prop('BackpackContainer','ZStructProperty',Struct=ct),
                     BackpackItems=prop('BackpackItems','ZStructProperty',Struct=slots))
        self.field=Obj(_type=at, Value=70, BaseValue=16)
        self.ps=Obj(Class=psclass, BackpackContainer=Obj(_type=ct,MaxSize=self.field,ProfileId=1),
                    BackpackItems=Obj(_type=slots,items=[Obj(_type=slot,InventoryItem=Obj(_type=it,Handle=Obj(_type=ht,Handle=i),EquipSlot=-1)) for i in range(4)]))
        def op(name, target): return prop(name,'ZObjectProperty',PropertyClass=N(Name=target))
        def arr(name, target): return prop(name,'ZArrayProperty',Inner=op('Inner',target))
        self.state=Obj(Class=st('OakGameState',PlayerArray=arr('PlayerArray','PlayerState')),PlayerArray=[self.ps])
        self.pawn=Obj()
        self.pc=Obj(PlayerState=self.ps)
        self.manager=Obj(PCOwner=self.pc);self.pc.PlayerCameraManager=self.manager
        self.camera=Obj(CameraOwner=self.manager)
        self.lp=Obj(Class=st('LocalPlayer',PlayerController=op('PlayerController','PlayerController')),PlayerController=self.pc)
        self.gi=Obj(Class=st('OakGameInstance',LocalPlayers=arr('LocalPlayers','LocalPlayer')),LocalPlayers=[self.lp])
        self.world=Obj(Class=st('World',GameState=op('GameState','GameStateBase'),OwningGameInstance=op('OwningGameInstance','GameInstance')),GameState=self.state,OwningGameInstance=self.gi)
        self.viewport=Obj(Class=st('GameViewportClient',World=op('World','World')),World=self.world)
        self.mods=N(ENGINE=N(GameViewport=self.viewport))
        self.standalone=True;self.eligible=True
        self.api=(lambda _:self.standalone,None,None,None,lambda _:self.state)
        self.f=N(mod=N(is_enabled=True),auto_master=N(value=False),_auto_owned=set(),
                 _activation_request=None,_auto_ground=None,conflicting_mods=lambda:False,
                 _controller=None,_monitor_registered=True,_monitor_error='',
                 _monitor_thread=threading.get_ident(),_monitor_seen=time.monotonic(),
                 _MONITOR_PATH='p',_MONITOR_ID='i',
                 current_session=lambda api:(self.pc,self.pawn,self.state,self.eligible),
                 bound_session=lambda sdk:self.api)
        self.sdk=N(unreal=N(BoundFunction=BoundFunction,UFunction=UFunction,WeakPointer=WeakPointer),
                   hooks=N(Type=N(POST_UNCONDITIONAL=1),has_hook=lambda *args:True))
        self.bound=BoundFunction(func=UFunction(),object=self.camera)
        self.shot=a.OneShot()

    def fire(self): return self.shot.callback(self.camera,None,None,self.bound)


class Tests(unittest.TestCase):
    def setUp(self):
        self.x=Fixture();x=self.x
        self.modules=patch.dict(sys.modules, {'mods_base':x.mods,'unrealsdk':x.sdk});self.modules.start()
        self.foundation=patch.object(a,'exact_foundation',return_value=x.f);self.foundation.start()
        self.addCleanup(self.modules.stop);self.addCleanup(self.foundation.stop)
        self.addCleanup(lambda: sys.__dict__.pop(a.LATCH,None))
        sys.__dict__.pop(a.LATCH,None)

    def arm(self): self.assertTrue(self.x.shot.arm('backpack',CONFIRM))

    def reject(self):
        self.assertIsNone(self.x.fire());self.assertIsNone(self.x.shot.result)
        self.assertIn('HOLD/FAULT',self.x.shot.status);self.assertEqual(self.x.field.Value,70)
        self.assertFalse(self.x.shot.arm('backpack',CONFIRM))

    def test_success_one_shot(self):
        self.arm();self.assertIsNone(self.x.fire());self.assertEqual(self.x.shot.result,(70,71,70))
        self.assertEqual(self.x.field.BaseValue,16);self.assertFalse(a.OneShot().arm('backpack',CONFIRM))
        self.assertIsNone(self.x.fire());self.assertEqual(self.x.field.Value,70)

    def test_wrong_confirmation_not_armed(self):
        self.assertFalse(self.x.shot.arm('backpack','wrong'));self.assertIsNone(self.x.fire())
        self.assertFalse(getattr(sys,a.LATCH,False));self.arm()

    def test_idle_failure_consumes_latch(self):
        self.x.f.auto_master.value=True;self.assertFalse(self.x.shot.arm('backpack',CONFIRM))
        self.x.f.auto_master.value=False;self.assertFalse(self.x.shot.arm('backpack',CONFIRM))

    def test_listen_host(self):
        self.arm();self.x.standalone=False;self.reject()

    def test_eligible_false(self):
        self.arm();self.x.eligible=False;self.reject()

    def test_second_player(self):
        self.arm();self.x.state.PlayerArray.append(Obj());self.reject()

    def test_wrong_sole_player(self):
        self.arm();self.x.state.PlayerArray=[Obj()];self.reject()

    def test_second_local_player(self):
        self.arm();self.x.gi.LocalPlayers.append(Obj());self.reject()

    def test_world_state_mismatch(self):
        self.arm();self.x.world.GameState=Obj();self.reject()

    def test_camera_mismatch(self):
        self.arm();self.x.bound.object=Obj();self.reject()

    def test_stale_monitor(self):
        self.arm();self.x.f._monitor_seen-=5;self.reject()

    def test_expired(self):
        self.arm();self.x.shot.pending=(*self.x.shot.pending[:-1],time.monotonic()-1);self.reject()

    def test_disarm(self):
        self.arm();self.x.shot.disarm();self.assertIsNone(self.x.fire())
        self.assertIsNone(self.x.shot.result);self.assertFalse(self.x.shot.arm('backpack',CONFIRM))

    def test_bad_property_descriptor(self):
        self.arm();self.x.field._type.props['Value'].ArrayDim=2;self.reject()

    def test_wrapper_descriptor_mismatch(self):
        self.arm();self.x.field._type=st('GbxAttributeInteger');self.reject()

    def test_wrong_thread(self):
        self.arm();t=threading.Thread(target=self.x.fire);t.start();t.join()
        self.assertIsNone(self.x.shot.result);self.assertIn('wrong thread',self.x.shot.status)
        self.assertEqual(self.x.field.Value,70)

    def test_replaced_world_before_write(self):
        self.arm();x=self.x;orig=a.reflection_stamp;calls=0
        def changed(ps,kind):
            nonlocal calls
            v=orig(ps,kind);calls+=1
            if calls==1: x.viewport.World=Obj(Class=x.world.Class,GameState=x.state,OwningGameInstance=x.gi)
            return v
        with patch.object(a,'reflection_stamp',side_effect=changed): self.reject()

    def test_dead_weak_pointer(self):
        self.arm();x=self.x
        class Dead(WeakPointer):
            def __call__(self): return None if self.obj is x.ps else self.obj
        x.sdk.unreal.WeakPointer=Dead;self.reject()

    def test_replaced_embedded_wrapper_before_write(self):
        self.arm();x=self.x;orig=a.reflection_stamp;calls=0
        def changed(ps,kind):
            nonlocal calls
            v=orig(ps,kind);calls+=1
            if calls==1: ps.BackpackContainer=Obj(_type=ps.BackpackContainer._type,MaxSize=x.field,ProfileId=1)
            return v
        with patch.object(a,'reflection_stamp',side_effect=changed): self.reject()

    def test_backpack_occupancy_excludes_equipped_and_empty(self):
        items=self.x.ps.BackpackItems.items
        items[0].InventoryItem.EquipSlot=0
        items[1].InventoryItem.Handle.Handle=-1
        self.assertEqual(a.occupancy_stamp(self.x.ps,'backpack')[0],2)
        self.arm();self.x.fire();self.assertEqual(self.x.shot.result,(70,71,70))

    def test_duplicate_handle_refused(self):
        self.arm();items=self.x.ps.BackpackItems.items
        items[0].InventoryItem.Handle.Handle=items[1].InventoryItem.Handle.Handle
        self.reject()

    def test_same_length_item_change_refused(self):
        self.arm();x=self.x;orig=a.occupancy_stamp;calls=0
        def changed(ps,kind):
            nonlocal calls
            v=orig(ps,kind);calls+=1
            if calls==1: ps.BackpackItems.items[0].InventoryItem.Handle.Handle=888
            return v
        with patch.object(a,'occupancy_stamp',side_effect=changed): self.reject()

    def test_world_descriptor_wrong(self):
        self.arm();self.x.world.Class.props['GameState'].PropertyClass.Name='Wrong';self.reject()

    def test_nested_handle_descriptor_wrong(self):
        self.arm();self.x.ps.BackpackItems.items[0].InventoryItem.Handle._type.props['Handle'].ArrayDim=2;self.reject()

    def test_nested_wrapper_wrong(self):
        self.arm();self.x.ps.BackpackItems.items[0]._type=st('GbxItemContainerSlot');self.reject()

    def test_equipment_must_be_signed_integer(self):
        self.arm();self.x.ps.BackpackItems.items[0].InventoryItem.EquipSlot='-1';self.reject()

    def test_bank_readback_with_distinct_structs(self):
        x=self.x;ps=x.ps;ct=ps.BackpackContainer._type;stt=ps.BackpackItems._type
        ps.Class.props['BankContainer']=prop('BankContainer','ZStructProperty',Struct=ct)
        ps.Class.props['BankItems']=prop('BankItems','ZStructProperty',Struct=stt)
        field=Obj(_type=x.field._type, Value=100, BaseValue=25)
        ps.BankContainer=Obj(_type=ct,MaxSize=field,ProfileId=2)
        ps.BankItems=Obj(_type=stt,items=list(ps.BackpackItems.items))
        self.assertTrue(x.shot.arm('bank',CONFIRM));x.fire()
        self.assertEqual(x.shot.result,(100,101,100));self.assertEqual(x.field.Value,70)

    def test_bank_occupied_equip_rejected(self):
        ps=self.x.ps;ps.BankItems=ps.BackpackItems
        ps.BankItems.items[0].InventoryItem.EquipSlot=0
        with self.assertRaises(a.CapacityFault): a.occupancy_stamp(ps,'bank')

if __name__=='__main__': unittest.main()
