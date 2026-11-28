"""Synthetic regression tests for upgraded calibrated automatic equipment pickup."""
import types
import unittest
from test_foundation import Test as FoundationTest


class Node(types.SimpleNamespace):
    def _get_address(self):
        return id(self)


def make_prop(name, cls_name, **extra):
    cls = type(cls_name, (), {})
    obj = cls()
    obj.Name = name
    obj.ArrayDim = 1
    for k, v in extra.items():
        setattr(obj, k, v)
    return obj


def make_type(path, props=()):
    return Node(_path_name=lambda: path, _properties=lambda: list(props), Name=path.rsplit('.', 1)[-1])


class FakeEnum:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return self.name


class GearPickupTests(unittest.TestCase):
    def setUp(self):
        self._base = FoundationTest()
        self._base.setUp()
        self.addCleanup(self._base.doCleanups)
        from bl4_custom_foundation import gear_pickup as G
        from bl4_custom_foundation.loot_vacuum import HIGH_GEAR_COLORS, PALETTE
        self.G = G
        self.HIGH_GEAR_COLORS = HIGH_GEAR_COLORS
        self.PALETTE = PALETTE
        self.tid = 101
        self.time = 10.0
        self.ok = True
        self.permitted = True
        self.vacuum_busy = False
        self.reports = []
        self.dispatches = []
        self.primary = FakeEnum('Primary', 0)
        self.secondary = FakeEnum('Secondary', 1)
        self._next_handle = 100

        # ServerUseObject UFunction
        pc_outer = Node(_path_name=lambda: G.PC_CLASS)
        obj_cls = Node(_path_name=lambda: '/Script/CoreUObject.Object')
        enum_cls = Node(_path_name=lambda: G.USABILITY_ENUM)
        self.use_fn = Node(
            Name='ServerUseObject',
            Outer=pc_outer,
            NumParams=3,
            _path_name=lambda: G.USE_OBJECT_PATH,
            _properties=lambda: [
                make_prop('Usable', 'ZObjectProperty', PropertyClass=obj_cls),
                make_prop('UseType', 'ZEnumProperty', Enum=enum_cls),
                make_prop('bWasHeld', 'ZBoolProperty'),
            ],
        )

        # Typed backpack item & handle structs
        self.handle_t = make_type(G.HANDLE_STRUCT, [make_prop('Handle', 'ZIntProperty')])
        self.item_t = make_type(G.ITEM_STRUCT, [
            make_prop('Handle', 'ZStructProperty', Struct=self.handle_t),
            make_prop('EquipSlot', 'ZInt8Property'),
        ])
        self.slot_struct = make_type('/Script/GbxGame.GbxItemContainerSlot', [
            make_prop('InventoryItem', 'ZStructProperty', Struct=self.item_t),
        ])
        attr_t = make_type('/Script/GbxCore.GbxAttributeInteger', [
            make_prop('Value', 'ZIntProperty'),
            make_prop('BaseValue', 'ZIntProperty'),
        ])
        self.bp_max = Node(_type=attr_t, Value=5, BaseValue=5)
        self.bank_max = Node(_type=attr_t, Value=20, BaseValue=20)
        cont_t = make_type('/Script/GbxGame.GbxItemContainer', [
            make_prop('MaxSize', 'ZStructProperty', Struct=attr_t),
        ])
        self.bp_cont = Node(_type=cont_t, MaxSize=self.bp_max)
        self.bank_cont = Node(_type=cont_t, MaxSize=self.bank_max)
        slots_t = make_type('/Script/GbxGame.GbxItemSlotsContainer', [
            make_prop('items', 'ZArrayProperty', Inner=make_prop('items', 'ZStructProperty', Struct=self.slot_struct)),
        ])
        self.bp_items = Node(_type=slots_t, items=[self.make_bp_slot(1), self.make_bp_slot(2)])
        self.bank_items = Node(_type=slots_t, items=[])

        ps_t = make_type('/Script/OakGame.OakPlayerState', [
            make_prop('BackpackContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BankContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BackpackItems', 'ZStructProperty', Struct=slots_t),
            make_prop('BankItems', 'ZStructProperty', Struct=slots_t),
        ])
        self.ps = Node(
            Class=ps_t, _type=ps_t,
            _path_name=lambda: '/Game/World.OakPlayerState_0',
            BackpackContainer=self.bp_cont, BankContainer=self.bank_cont,
            BackpackItems=self.bp_items, BankItems=self.bank_items, Owner=None,
        )

        # EquippedInventorySlots (ALL categories: weapon, shield, repkit, class mod, etc.)
        self.eq_slot_t = make_type(G.EQUIPPED_SLOT, [
            make_prop('SourceItemHandle', 'ZStructProperty', Struct=self.handle_t),
            make_prop('bLocked', 'ZBoolProperty'),
        ])
        self.eq_cont_t = make_type(G.EQUIPPED_CONTAINER, [
            make_prop('items', 'ZArrayProperty', Inner=make_prop('items', 'ZStructProperty', Struct=self.eq_slot_t)),
        ])
        self.shield_inst = Node(_path_name=lambda: '/Game/World.EquippedShield_0')
        self.eq_slots = [
            Node(_type=self.eq_slot_t, SourceItemHandle=Node(_type=self.handle_t, Handle=10), bLocked=False, InstancedInventory=self.shield_inst),
        ]
        # ActiveWeapons.Slots
        w_cls = Node(Name='Weapon')
        slot_entry_t = make_type('/Script/GbxWeapon.ActiveWeaponSlot', [
            make_prop('Weapon', 'ZObjectProperty', PropertyClass=w_cls),
            make_prop('PendingWeapon', 'ZObjectProperty', PropertyClass=w_cls),
            make_prop('ClientPredictedPendingWeapon', 'ZObjectProperty', PropertyClass=w_cls),
        ])
        active_t = make_type('/Script/OakGame.OakActiveWeaponsState', [
            make_prop('Slots', 'ZArrayProperty', Inner=make_prop('Slots', 'ZStructProperty', Struct=slot_entry_t)),
        ])
        self.weapon0 = Node(_path_name=lambda: '/Game/World.Weapon_0')
        self.weapon_slots = [Node(_type=slot_entry_t, Weapon=self.weapon0, PendingWeapon=None, ClientPredictedPendingWeapon=None)]
        pawn_t = make_type('/Script/OakGame.OakCharacter', [
            make_prop('ActiveWeapons', 'ZStructProperty', Struct=active_t),
            make_prop('EquippedInventorySlots', 'ZStructProperty', Struct=self.eq_cont_t),
        ])
        self.pawn = Node(
            Class=pawn_t, _type=pawn_t,
            _path_name=lambda: '/Game/World.OakCharacter_0',
            PlayerState=self.ps,
            ActiveWeapons=Node(_type=active_t, Slots=self.weapon_slots),
            EquippedInventorySlots=Node(_type=self.eq_cont_t, items=self.eq_slots),
        )

        self.equip_shield_on_use = False
        self.consume_on_use = True
        self.cal_hook_ref = None
        pc_t = make_type(G.PC_CLASS)

        def server_use(usable, use_type, was_held):
            args = Node(Usable=usable, UseType=use_type, bWasHeld=was_held)
            if self.cal_hook_ref is not None:
                self.cal_hook_ref.on_pre(self.pc, args)
            self.dispatches.append((usable, use_type, was_held))
            if self.equip_shield_on_use:
                self.eq_slots[0].SourceItemHandle.Handle = 999
            elif self.consume_on_use:
                self._next_handle += 1
                self.bp_items.items.append(self.make_bp_slot(self._next_handle, equip_slot=-1))
                usable.UsableActorState.bInteractabilityLockedReplicated = True
            if self.cal_hook_ref is not None:
                self.cal_hook_ref.on_post(self.pc, args)

        class BoundMethod:
            def __init__(self, fn, cb):
                self.func = fn
                self._cb = cb

            def __call__(self, *a):
                return self._cb(*a)

        self.pc = Node(
            Class=pc_t, _path_name=lambda: '/Game/World.OakPlayerController_0',
            PlayerState=self.ps, Pawn=self.pawn, HasAuthority=lambda: True,
            ServerUseObject=BoundMethod(self.use_fn, server_use),
        )
        self.ps.Owner = self.pc

        self.usable_state_t = make_type(G.USABLE_STATE, [make_prop('bInteractabilityLockedReplicated', 'ZBoolProperty')])
        self.pickup_cls = make_type(G.PICKUP, [make_prop('UsableActorState', 'ZStructProperty', Struct=self.usable_state_t)])
        self.pickups = []
        self.colors = {}
        self.kinds = {}
        self.categories = {}
        self.item_ids = {}
        self.distances = {}
        self.live_refs = {}

    def make_bp_slot(self, handle_id, equip_slot=-1):
        h = Node(_type=self.handle_t, Handle=handle_id)
        inv = Node(_type=self.item_t, Handle=h, EquipSlot=equip_slot)
        return Node(_type=self.slot_struct, InventoryItem=inv)

    def make_pickup(self, name, kind='gear', category='Weapons', color=None, item_id='id_0', dist=200.0, locked=False):
        state = Node(_type=self.usable_state_t, bInteractabilityLockedReplicated=locked)
        actor = Node(Class=self.pickup_cls, _type=self.pickup_cls, _path_name=lambda n=name: f'/Game/World.{n}', UsableActorState=state)
        self.kinds[id(actor)] = kind
        self.categories[id(actor)] = category
        self.colors[id(actor)] = color if color is not None else self.HIGH_GEAR_COLORS[0]
        self.item_ids[id(actor)] = item_id
        self.distances[id(actor)] = dist
        self.live_refs[id(actor)] = actor
        return actor

    def weak(self, obj):
        oid = id(obj)
        self.live_refs[oid] = obj
        return lambda: self.live_refs.get(oid)

    def context(self):
        return self.pc, self.pawn, self.ps, self.ok

    def calibrator(self):
        return self.G.ManualPickupCalibrator(
            self.context, self.weak,
            lambda a: self.kinds.get(id(a)),
            lambda a: self.categories.get(id(a)),
            lambda a: self.item_ids.get(id(a)),
            lambda: self.time, lambda: self.tid, self.reports.append,
        )

    def collector(self, cal, *, high_only=False):
        return self.G.GearPickupCollector(
            self.context, self.weak, self.use_fn, cal,
            lambda: list(self.pickups),
            lambda a: self.kinds.get(id(a)),
            lambda a: self.categories.get(id(a)),
            lambda a: self.colors.get(id(a)),
            lambda a: self.item_ids.get(id(a)),
            lambda p, a: self.distances.get(id(a), 9999.0),
            lambda: self.time, lambda: self.tid, self.reports.append,
            lambda: self.permitted,
            vacuum_contending=lambda: self.vacuum_busy,
            high_only=high_only,
        )

    def calibrate_manual_tap(self, cal, category='Weapons'):
        sample = self.make_pickup(f'Manual_{category}', kind='gear', category=category, item_id=f'serial_{category}')
        args = Node(Usable=sample, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, equip_slot=-1))
        sample.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args)
        return sample

    def test_per_category_calibration_and_expiry(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons')
        shield = self.make_pickup('Shield_0', category='Shields', item_id='id_shield', dist=100.0)
        weapon = self.make_pickup('Weapon_0', category='Weapons', item_id='id_weapon', dist=200.0)
        self.pickups = [shield, weapon]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        # Shield is NOT calibrated yet -> collects Weapon only
        self.assertTrue(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        self.assertIs(self.dispatches[0][0], weapon)
        # Advance past 300s calibration lifetime -> calibration expires
        self.time += 350.0
        weapon2 = self.make_pickup('Weapon_1', category='Weapons', item_id='id_weapon2', dist=100.0)
        self.pickups = [weapon2]
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)

    def test_calibration_rejects_shield_equip_change_and_mismatched_post_and_stale_pre(self):
        cal = self.calibrator()
        # 1. Shield equipped slot changed -> rejected
        s1 = self.make_pickup('Shield_Eq', category='Shields', item_id='id_s1')
        args1 = Node(Usable=s1, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args1)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, equip_slot=-1))
        self.eq_slots[0].SourceItemHandle.Handle = 777
        s1.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args1)
        self.assertEqual(cal.calibrated_by_category, {})

        # 2. Mismatched POST Usable -> rejected
        w1 = self.make_pickup('W1', category='Weapons', item_id='id_w1')
        w2 = self.make_pickup('W2', category='Weapons', item_id='id_w2')
        cal.on_pre(self.pc, Node(Usable=w1, UseType=self.primary, bWasHeld=False))
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, equip_slot=-1))
        w1.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, Node(Usable=w2, UseType=self.primary, bWasHeld=False))
        self.assertEqual(cal.calibrated_by_category, {})

        # 3. Early return in PRE clears stale pending
        w3 = self.make_pickup('W3', category='Weapons', item_id='id_w3')
        cal.on_pre(self.pc, Node(Usable=w3, UseType=self.primary, bWasHeld=False))
        self.assertIsNotNone(cal.pending)
        cal.on_pre(self.pc, Node(Usable=w3, UseType=self.primary, bWasHeld=True))
        self.assertIsNone(cal.pending)

    def test_exact_handle_and_equip_slot_and_uncertain_acquisition_stops(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons')
        # Uncertain acquisition (server_use does not add handle or lock actor) -> stops, returns False, never retries
        self.consume_on_use = False
        w = self.make_pickup('W_Fail', category='Weapons', item_id='id_fail', dist=100.0)
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertIsNone(col.record)
        self.assertEqual(col.collected_count, 0)

    def test_self_calibration_prevented_and_shield_equip_faults(self):
        cal = self.calibrator()
        self.cal_hook_ref = cal
        self.calibrate_manual_tap(cal, category='Weapons')
        # Collector dispatches on Weapon -> must not refresh/self-calibrate
        w = self.make_pickup('W_Self', category='Weapons', item_id='id_self', dist=100.0)
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        expires_before = cal.calibrated_by_category['Weapons'][3]
        self.time += 5.0
        self.assertTrue(col.tick(True))
        self.assertEqual(cal.calibrated_by_category['Weapons'][3], expires_before)

        # Shield equip change during collection -> FAULT & halt
        self.equip_shield_on_use = True
        w2 = self.make_pickup('W_Fault', category='Weapons', item_id='id_fault', dist=100.0)
        self.pickups = [w2]
        self.time += 1.0
        self.assertFalse(col.tick(True))
        self.assertTrue(col.fault)
        self.assertIsNone(col.record)

    def test_vacuum_contention_yields_cleanly(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons')
        w = self.make_pickup('W_Vac', category='Weapons', item_id='id_vac', dist=100.0)
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.vacuum_busy = True
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 0)
        self.vacuum_busy = False
        self.time += 1.0
        self.assertTrue(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)


if __name__ == '__main__':
    unittest.main()
