"""Synthetic regression tests for Batch 3 calibrated automatic equipment collection."""
import types
import unittest
from test_foundation import Test as FoundationTest
from test_f8_simple import SimpleF8


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
        self._next_handle = 100

        # ServerUseObject UFunction
        pc_outer = Node(_path_name=lambda: G.PC_CLASS)
        obj_cls = Node(_path_name=lambda: '/Script/CoreUObject.Object')
        enum_cls = Node(_path_name=lambda: G.USABILITY_ENUM)
        self.use_fn = Node(
            Name='ServerUseObject', Outer=pc_outer, NumParams=3,
            _path_name=lambda: G.USE_OBJECT_PATH,
            _properties=lambda: [
                make_prop('Usable', 'ZObjectProperty', PropertyClass=obj_cls),
                make_prop('UseType', 'ZEnumProperty', Enum=enum_cls),
                make_prop('bWasHeld', 'ZBoolProperty'),
            ],
        )

        # Typed FGbxItem / FGbxItemData / FGbxItemState / FInventoryItem / FInventoryItemHandle
        self.gbx_data_t = make_type(G.GBX_ITEM_DATA, [make_prop('InstanceId', 'ZUInt32Property')])
        self.gbx_state_t = make_type(G.GBX_ITEM_STATE, [make_prop('Quantity', 'ZUInt32Property')])
        self.gbx_item_t = make_type(G.GBX_ITEM_STRUCT, [
            make_prop('data', 'ZStructProperty', Struct=self.gbx_data_t),
            make_prop('State', 'ZStructProperty', Struct=self.gbx_state_t),
        ])
        self.handle_t = make_type(G.HANDLE_STRUCT, [make_prop('Handle', 'ZIntProperty')])
        self.item_t = make_type(G.ITEM_STRUCT, [
            make_prop('item', 'ZStructProperty', Struct=self.gbx_item_t),
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
        self.bp_items = Node(_type=slots_t, items=[self.make_bp_slot(1, 501, 1), self.make_bp_slot(2, 502, 1)])
        self.bank_items = Node(_type=slots_t, items=[])

        ps_t = make_type('/Script/OakGame.OakPlayerState', [
            make_prop('BackpackContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BankContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BackpackItems', 'ZStructProperty', Struct=slots_t),
            make_prop('BankItems', 'ZStructProperty', Struct=slots_t),
        ])
        self.ps = Node(
            Class=ps_t, _type=ps_t, _path_name=lambda: '/Game/World.OakPlayerState_0',
            BackpackContainer=self.bp_cont, BankContainer=self.bank_cont,
            BackpackItems=self.bp_items, BankItems=self.bank_items, Owner=None,
        )

        # EquippedInventorySlots + ActiveWeapons.Slots
        self.eq_slot_t = make_type(G.EQUIPPED_SLOT, [
            make_prop('SourceItemHandle', 'ZStructProperty', Struct=self.handle_t),
            make_prop('bLocked', 'ZBoolProperty'),
        ])
        self.eq_cont_t = make_type(G.EQUIPPED_CONTAINER, [
            make_prop('items', 'ZArrayProperty', Inner=make_prop('items', 'ZStructProperty', Struct=self.eq_slot_t)),
        ])
        self.eq_slots = [
            Node(_type=self.eq_slot_t, SourceItemHandle=Node(_type=self.handle_t, Handle=10), bLocked=False, InstancedInventory=Node()),
        ]
        w_cls = Node(Name='Weapon')
        slot_entry_t = make_type('/Script/GbxWeapon.ActiveWeaponSlot', [
            make_prop('Weapon', 'ZObjectProperty', PropertyClass=w_cls),
            make_prop('PendingWeapon', 'ZObjectProperty', PropertyClass=w_cls),
            make_prop('ClientPredictedPendingWeapon', 'ZObjectProperty', PropertyClass=w_cls),
        ])
        active_t = make_type('/Script/OakGame.OakActiveWeaponsState', [
            make_prop('Slots', 'ZArrayProperty', Inner=make_prop('Slots', 'ZStructProperty', Struct=slot_entry_t)),
        ])
        self.weapon_slots = [Node(_type=slot_entry_t, Weapon=Node(), PendingWeapon=None, ClientPredictedPendingWeapon=None)]
        pawn_t = make_type('/Script/OakGame.OakCharacter', [
            make_prop('ActiveWeapons', 'ZStructProperty', Struct=active_t),
            make_prop('EquippedInventorySlots', 'ZStructProperty', Struct=self.eq_cont_t),
        ])
        self.pawn = Node(
            Class=pawn_t, _type=pawn_t, _path_name=lambda: '/Game/World.OakCharacter_0',
            PlayerState=self.ps,
            ActiveWeapons=Node(_type=active_t, Slots=self.weapon_slots),
            EquippedInventorySlots=Node(_type=self.eq_cont_t, items=self.eq_slots),
        )

        self.sync_deliver = True
        self.wrong_instance_deliver = False
        self.mutate_existing_deliver = False
        self.cal_hook_ref = None
        pc_t = make_type(G.PC_CLASS)

        def server_use(usable, use_type, was_held):
            args = Node(Usable=usable, UseType=use_type, bWasHeld=was_held)
            if self.cal_hook_ref is not None:
                self.cal_hook_ref.on_pre(self.pc, args)
            self.dispatches.append((usable, use_type, was_held))
            if self.sync_deliver:
                self._next_handle += 1
                inst_id = usable.item.data.InstanceId + (999 if self.wrong_instance_deliver else 0)
                qty = usable.item.State.Quantity
                if self.mutate_existing_deliver:
                    self.bp_items.items[0].InventoryItem.item.State.Quantity += 1
                self.bp_items.items.append(self.make_bp_slot(self._next_handle, inst_id, qty, equip_slot=-1))
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
        self.pickup_cls = make_type(G.PICKUP, [
            make_prop('UsableActorState', 'ZStructProperty', Struct=self.usable_state_t),
            make_prop('item', 'ZStructProperty', Struct=self.gbx_item_t),
        ])
        self.pickups = []
        self.colors = {}
        self.kinds = {}
        self.categories = {}
        self.distances = {}
        self.live_refs = {}

    def make_gbx_item(self, inst_id, qty):
        return Node(
            _type=self.gbx_item_t,
            data=Node(_type=self.gbx_data_t, InstanceId=inst_id),
            State=Node(_type=self.gbx_state_t, Quantity=qty),
        )

    def make_bp_slot(self, handle_id, inst_id, qty, equip_slot=-1):
        h = Node(_type=self.handle_t, Handle=handle_id)
        inv = Node(_type=self.item_t, item=self.make_gbx_item(inst_id, qty), Handle=h, EquipSlot=equip_slot)
        return Node(_type=self.slot_struct, InventoryItem=inv)

    def make_pickup(self, name, inst_id, qty=1, kind='gear', category='Weapons', color=None, dist=200.0, locked=False):
        state = Node(_type=self.usable_state_t, bInteractabilityLockedReplicated=locked)
        actor = Node(
            Class=self.pickup_cls, _type=self.pickup_cls,
            _path_name=lambda n=name: f'/Game/World.{n}',
            UsableActorState=state,
            item=self.make_gbx_item(inst_id, qty),
        )
        self.kinds[id(actor)] = kind
        self.categories[id(actor)] = category
        self.colors[id(actor)] = color if color is not None else self.HIGH_GEAR_COLORS[0]
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
            lambda: self.time, lambda: self.tid, self.reports.append,
        )

    def collector(self, cal, *, high_only=False):
        return self.G.GearPickupCollector(
            self.context, self.weak, self.use_fn, cal,
            lambda: list(self.pickups),
            lambda a: self.kinds.get(id(a)),
            lambda a: self.categories.get(id(a)),
            lambda a: self.colors.get(id(a)),
            lambda p, a: self.distances.get(id(a), 9999.0),
            lambda: self.time, lambda: self.tid, self.reports.append,
            lambda: self.permitted,
            vacuum_contending=lambda: self.vacuum_busy,
            high_only=high_only,
        )

    def calibrate_manual_tap(self, cal, category='Weapons', inst_id=9001, qty=1):
        sample = self.make_pickup(f'Manual_{category}', inst_id, qty, category=category)
        args = Node(Usable=sample, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, inst_id, qty, equip_slot=-1))
        sample.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args)
        return sample

    def test_exact_ground_to_backpack_instance_id_and_quantity_matching(self):
        cal = self.calibrator()
        # Wrong InstanceId inserted into backpack -> calibration REJECTED!
        sample_bad = self.make_pickup('Manual_WrongId', inst_id=7001, qty=1)
        args_bad = Node(Usable=sample_bad, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args_bad)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, 7999, 1, equip_slot=-1))
        sample_bad.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args_bad)
        self.assertEqual(cal.calibrated_by_category, {})

        # Exact InstanceId + Quantity match -> calibration SUCCEEDS
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7002, qty=1)
        self.assertIn('Weapons', cal.calibrated_by_category)

        # Collector acquires exact matching ground item
        w = self.make_pickup('Ground_Exact', inst_id=8001, qty=1, category='Weapons')
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertTrue(col.tick(True))
        self.assertEqual(col.collected_count, 1)
        self.assertEqual(len(self.dispatches), 1)

    def test_mutated_existing_backpack_entry_rejected(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7100)
        self.mutate_existing_deliver = True
        w = self.make_pickup('Ground_Mutate', inst_id=8100, category='Weapons')
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        # Synchronous match fails because prior entry mutated -> parks pending_receipt, times out & stops
        self.assertFalse(col.tick(True))
        self.assertIsNotNone(col.pending_receipt)
        self.time += 3.0
        self.assertFalse(col.tick(True))
        self.assertIsNone(col.record)
        self.assertEqual(len(self.dispatches), 1)

    def test_delayed_async_acquisition_receipt_confirms_without_duplicate_request(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7200)
        self.sync_deliver = False
        w1 = self.make_pickup('Ground_Async1', inst_id=8201, category='Weapons', dist=100.0)
        w2 = self.make_pickup('Ground_Async2', inst_id=8202, category='Weapons', dist=150.0)
        self.pickups = [w1, w2]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        # Dispatch w1 asynchronously -> pending_receipt active, no second dispatch
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        self.assertIsNotNone(col.pending_receipt)
        # Intermediate tick before delivery -> still waiting, no duplicate dispatch
        self.time += 0.5
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        # Native server completes delivery asynchronously
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, 8201, 1, equip_slot=-1))
        w1.UsableActorState.bInteractabilityLockedReplicated = True
        self.time += 0.5
        self.assertTrue(col.tick(True))
        self.assertIsNone(col.pending_receipt)
        self.assertEqual(col.collected_count, 1)
        self.assertEqual(len(self.dispatches), 1)

    def test_delayed_receipt_timeout_stops_without_retry(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7300)
        self.sync_deliver = False
        w = self.make_pickup('Ground_Timeout', inst_id=8301, category='Weapons')
        self.pickups = [w]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        self.time += 2.5
        self.assertFalse(col.tick(True))
        self.assertIsNone(col.record)
        self.assertEqual(len(self.dispatches), 1)

    def test_fresh_pre_dispatch_distance_recheck_blocks_moved_pickup(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7400)
        w = self.make_pickup('Ground_Move', inst_id=8401, category='Weapons', dist=100.0)
        self.pickups = [w]
        calls = [0]

        def dynamic_dist(p, a):
            calls[0] += 1
            return 100.0 if calls[0] == 1 else 5000.0

        col = self.G.GearPickupCollector(
            self.context, self.weak, self.use_fn, cal,
            lambda: list(self.pickups),
            lambda a: self.kinds.get(id(a)),
            lambda a: self.categories.get(id(a)),
            lambda a: self.colors.get(id(a)),
            dynamic_dist,
            lambda: self.time, lambda: self.tid, self.reports.append,
            lambda: self.permitted,
        )
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 0)

    def test_equipped_inventory_slot_mutation_faults_and_blocks_calibration(self):
        cal = self.calibrator()
        sample = self.make_pickup('Manual_EquipChange', inst_id=7500, category='Weapons')
        args = Node(Usable=sample, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, 7500, 1, equip_slot=-1))
        # Simulate non-weapon EquippedInventorySlots mutation (e.g. shield/class mod changed)
        self.eq_slots[0].SourceItemHandle.Handle = 999
        sample.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args)
        self.assertEqual(cal.calibrated_by_category, {})

        # Now calibrate cleanly and verify collector faults if EquippedInventorySlots mutates during pickup
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7501)
        w = self.make_pickup('Ground_EquipFault', inst_id=8501, category='Weapons')
        self.pickups = [w]
        self.sync_deliver = False
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertIsNotNone(col.pending_receipt)
        # Mutate EquippedInventorySlots before receipt completes -> immediate FAULT
        self.eq_slots[0].SourceItemHandle.Handle = 1234
        self.time += 0.2
        self.assertFalse(col.tick(True))
        self.assertIsNone(col.record)
        self.assertTrue(any('FAULT' in r for r in self.reports))

    def test_category_isolation_and_self_calibration_guard(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7600)
        # Shield pickup must NOT be collected using Weapons calibration
        shield = self.make_pickup('Ground_Shield', inst_id=8601, category='Shields')
        self.pickups = [shield]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 0)

        # Self-dispatching guard: even if server_use triggers cal.on_pre/on_post, it must not self-calibrate
        self.cal_hook_ref = cal
        w = self.make_pickup('Ground_Weapon', inst_id=8602, category='Weapons')
        self.pickups = [w]
        prev_cal_entry = cal.calibrated_by_category['Weapons']
        self.time += 5.0
        self.assertTrue(col.tick(True))
        self.assertEqual(cal.calibrated_by_category['Weapons'], prev_cal_entry)

    def test_vacuum_contention_yields_without_dispatch(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal, category='Weapons', inst_id=7700)
        w = self.make_pickup('Ground_VacYield', inst_id=8701, category='Weapons')
        self.pickups = [w]
        self.vacuum_busy = True
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 0)
        # Once Loot Vacuum contention clears, collector acquires cleanly
        self.vacuum_busy = False
        self.time += 1.0
        self.assertTrue(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(col.collected_count, 1)

    def test_stale_pending_and_mismatched_post_args_rejected(self):
        cal = self.calibrator()
        w1 = self.make_pickup('Manual_A', inst_id=7801, category='Weapons')
        w2 = self.make_pickup('Manual_B', inst_id=7802, category='Weapons')
        args1 = Node(Usable=w1, UseType=self.primary, bWasHeld=False)
        args2 = Node(Usable=w2, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args1)
        self._next_handle += 1
        self.bp_items.items.append(self.make_bp_slot(self._next_handle, 7801, 1, equip_slot=-1))
        w1.UsableActorState.bInteractabilityLockedReplicated = True
        # Mismatched POST actor must be rejected and clear pending
        cal.on_post(self.pc, args2)
        self.assertEqual(cal.calibrated_by_category, {})
        self.assertIsNone(cal.pending)


class GearPickupF8UI(SimpleF8):
    def test_gear_pickup_in_existing_loot_vacuum_panel(self):
        m = self.m
        m._category = 5
        m._compact_view = False
        f = m.AUTOMATION_OPTIONS['gear_pickup']
        self.assertFalse(f.value)
        label = f.display_name + '##' + f.identifier
        labels = self.render()
        self.assertIn(label, labels)
        self.render({label: True})
        self.assertTrue(f.value)
        self.assertTrue(m.auto_master.value)
        self.render(clicks=['Restore All'])
        self.assertFalse(f.value)
        self.assertFalse(m.auto_master.value)

    def test_gear_pickup_observer_registration_and_rollback(self):
        import sys
        m = self.m
        from bl4_custom_foundation import gear_pickup as G
        sdk = sys.modules['unrealsdk']
        obj_cls = Node(_path_name=lambda: '/Script/CoreUObject.Object')
        enum_cls = Node(_path_name=lambda: G.USABILITY_ENUM)
        cdo = Node()
        pc_outer = Node(_path_name=lambda: G.PC_CLASS, ClassDefaultObject=cdo)
        use_fn = Node(
            Name='ServerUseObject', Outer=pc_outer, NumParams=3,
            _path_name=lambda: G.USE_OBJECT_PATH,
            _properties=lambda: [
                make_prop('Usable', 'ZObjectProperty', PropertyClass=obj_cls),
                make_prop('UseType', 'ZEnumProperty', Enum=enum_cls),
                make_prop('bWasHeld', 'ZBoolProperty'),
            ],
        )
        cdo.ServerUseObject = Node(func=use_fn)
        orig_find = sdk.find_all
        registered = {}

        class FakeHooks:
            class Type:
                PRE = 'PRE'
                POST_UNCONDITIONAL = 'POST_UNCONDITIONAL'

            fail_second = False

            @classmethod
            def has_hook(cls, p, t, i):
                return (p, t, i) in registered

            @classmethod
            def add_hook(cls, p, t, i, cb):
                if cls.fail_second and len(registered) == 1:
                    return False
                registered[(p, t, i)] = cb
                return True

            @classmethod
            def remove_hook(cls, p, t, i):
                registered.pop((p, t, i), None)
                return True

        orig_hooks = getattr(sdk, 'hooks', None)
        orig_att, orig_own = m._gear_pickup_observers_attempted, m._gear_pickup_observers_owned
        try:
            sdk.find_all = lambda cls_name, exact=False: [use_fn] if cls_name == 'Function' else []
            sdk.hooks = FakeHooks
            # 1. Partial registration failure rolls back first hook
            m._gear_pickup_observers_attempted = False
            m._gear_pickup_observers_owned = False
            FakeHooks.fail_second = True
            self.assertFalse(m.ensure_gear_pickup_observers(sdk))
            self.assertEqual(registered, {})
            # 2. Preexisting foreign hook refused
            m._gear_pickup_observers_attempted = False
            m._gear_pickup_observers_owned = False
            FakeHooks.fail_second = False
            registered[(G.USE_OBJECT_PATH, FakeHooks.Type.PRE, 'bl4_custom_gear_pickup_pre')] = lambda *a: None
            self.assertFalse(m.ensure_gear_pickup_observers(sdk))
            self.assertFalse(m.gear_pickup_observers_live())
            # 3. Clean registration succeeds
            registered.clear()
            m._gear_pickup_observers_attempted = False
            m._gear_pickup_observers_owned = False
            self.assertTrue(m.ensure_gear_pickup_observers(sdk))
            self.assertTrue(m.gear_pickup_observers_live())
        finally:
            sdk.find_all = orig_find
            if orig_hooks is not None:
                sdk.hooks = orig_hooks
            m._gear_pickup_observers_attempted = orig_att
            m._gear_pickup_observers_owned = orig_own


if __name__ == '__main__':
    unittest.main()
