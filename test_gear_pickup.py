"""Synthetic regression tests for calibrated automatic equipment pickup (ServerUseObject)."""
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
    t = Node(_path_name=lambda: path, _properties=lambda: list(props), Name=path.rsplit('.', 1)[-1])
    return t


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
        self.reports = []
        self.dispatches = []
        self.primary = FakeEnum('Primary', 0)
        self.secondary = FakeEnum('Secondary', 1)
        self.any_use = FakeEnum('Any', 2)

        # Build ServerUseObject UFunction
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

        # Backpack and Bank containers matching inventory_capacity.inspect
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
        slot_struct = make_type('/Script/GbxGame.GbxItemContainerSlot')
        slots_t = make_type('/Script/GbxGame.GbxItemSlotsContainer', [
            make_prop('items', 'ZArrayProperty', Inner=make_prop('items', 'ZStructProperty', Struct=slot_struct)),
        ])
        self.bp_items = Node(_type=slots_t, items=['item0', 'item1'])
        self.bank_items = Node(_type=slots_t, items=[])

        ps_t = make_type('/Script/OakGame.OakPlayerState', [
            make_prop('BackpackContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BankContainer', 'ZStructProperty', Struct=cont_t),
            make_prop('BackpackItems', 'ZStructProperty', Struct=slots_t),
            make_prop('BankItems', 'ZStructProperty', Struct=slots_t),
        ])
        self.ps = Node(
            Class=ps_t,
            _type=ps_t,
            _path_name=lambda: '/Game/World.OakPlayerState_0',
            BackpackContainer=self.bp_cont,
            BankContainer=self.bank_cont,
            BackpackItems=self.bp_items,
            BankItems=self.bank_items,
            Owner=None,
        )

        # Equipped weapon slots matching weapon_rates.slot_entries
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
        self.slots = [Node(_type=slot_entry_t, Weapon=self.weapon0, PendingWeapon=None, ClientPredictedPendingWeapon=None)]
        pawn_t = make_type('/Script/OakGame.OakCharacter', [
            make_prop('ActiveWeapons', 'ZStructProperty', Struct=active_t),
        ])
        self.pawn = Node(
            Class=pawn_t,
            _type=pawn_t,
            _path_name=lambda: '/Game/World.OakCharacter_0',
            PlayerState=self.ps,
            ActiveWeapons=Node(_type=active_t, Slots=self.slots),
        )

        self.equip_on_use = False
        self.consume_on_use = True
        pc_t = make_type(G.PC_CLASS)

        def server_use(usable, use_type, was_held):
            self.dispatches.append((usable, use_type, was_held))
            if self.equip_on_use:
                self.slots[0].Weapon = Node(_path_name=lambda: '/Game/World.EquippedNew')
            elif self.consume_on_use:
                self.bp_items.items.append(usable)
                usable.UsableActorState.bInteractabilityLockedReplicated = True

        bound = Node(func=self.use_fn, __call__=server_use)

        class BoundMethod:
            def __init__(self, fn, cb):
                self.func = fn
                self._cb = cb

            def __call__(self, *a):
                return self._cb(*a)

        self.pc = Node(
            Class=pc_t,
            _path_name=lambda: '/Game/World.OakPlayerController_0',
            PlayerState=self.ps,
            Pawn=self.pawn,
            HasAuthority=lambda: True,
            ServerUseObject=BoundMethod(self.use_fn, server_use),
        )
        self.ps.Owner = self.pc

        # UsableActorState schema
        self.usable_state_t = make_type(G.USABLE_STATE, [
            make_prop('bInteractabilityLockedReplicated', 'ZBoolProperty'),
        ])
        self.pickup_cls = make_type(G.PICKUP, [
            make_prop('UsableActorState', 'ZStructProperty', Struct=self.usable_state_t),
        ])
        self.pickups = []
        self.colors = {}
        self.kinds = {}
        self.item_ids = {}
        self.distances = {}
        self.live_refs = {}

    def make_pickup(self, name, kind='gear', color=None, item_id=None, dist=200.0, locked=False):
        state = Node(_type=self.usable_state_t, bInteractabilityLockedReplicated=locked)
        actor = Node(
            Class=self.pickup_cls,
            _type=self.pickup_cls,
            _path_name=lambda n=name: f'/Game/World.{n}',
            UsableActorState=state,
        )
        self.kinds[id(actor)] = kind
        self.colors[id(actor)] = color if color is not None else self.HIGH_GEAR_COLORS[0]
        if item_id is not None:
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
            self.context, self.weak, lambda a: self.kinds.get(id(a)),
            lambda: self.tid, self.reports.append,
        )

    def collector(self, cal, *, high_only=False, radius=1500.0):
        return self.G.GearPickupCollector(
            self.context, self.weak, self.use_fn, cal,
            lambda: list(self.pickups),
            lambda a: self.kinds.get(id(a)),
            lambda a: self.colors.get(id(a)),
            lambda a: self.item_ids.get(id(a)),
            lambda p, a: self.distances.get(id(a), 9999.0),
            lambda: self.time, lambda: self.tid, self.reports.append,
            radius=radius, high_only=high_only,
        )

    def calibrate_manual_tap(self, cal):
        sample = self.make_pickup('ManualGear_0', kind='gear', item_id='serial_manual')
        args = Node(Usable=sample, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args)
        self.bp_items.items.append(sample)
        sample.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args)
        return sample

    def test_bind_use_object_validates_signature(self):
        bound_fn, fn = self.G.bind_use_object([self.use_fn], lambda fs, p, s: ('bound', p))
        self.assertEqual(bound_fn, ('bound', self.G.USE_OBJECT_PATH))
        self.assertIs(fn, self.use_fn)
        bad = Node(Name='ServerUseObject', Outer=self.use_fn.Outer, NumParams=2, _path_name=lambda: self.G.USE_OBJECT_PATH, _properties=lambda: [])
        with self.assertRaises(ValueError):
            self.G.bind_use_object([bad], lambda fs, p, s: None)

    def test_uncalibrated_collector_holds(self):
        cal = self.calibrator()
        col = self.collector(cal)
        self.assertFalse(col.begin())
        self.assertTrue(any('calibrate' in r for r in self.reports))

    def test_calibration_rejects_held_and_equip_and_non_gear(self):
        cal = self.calibrator()
        # Held (equip) rejected
        g1 = self.make_pickup('Gear_Hold', kind='gear')
        args_hold = Node(Usable=g1, UseType=self.primary, bWasHeld=True)
        cal.on_pre(self.pc, args_hold)
        self.bp_items.items.append(g1)
        g1.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args_hold)
        self.assertIsNone(cal.calibrated)

        # Equipped slot changed rejected
        g2 = self.make_pickup('Gear_Equip', kind='gear')
        args_eq = Node(Usable=g2, UseType=self.secondary, bWasHeld=False)
        cal.on_pre(self.pc, args_eq)
        self.bp_items.items.append(g2)
        self.slots[0].Weapon = Node(_path_name=lambda: '/Game/World.Swapped')
        g2.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args_eq)
        self.assertIsNone(cal.calibrated)

        # Non-gear rejected
        cash = self.make_pickup('Cash_0', kind='cash')
        args_cash = Node(Usable=cash, UseType=self.primary, bWasHeld=False)
        cal.on_pre(self.pc, args_cash)
        self.bp_items.items.append(cash)
        cash.UsableActorState.bInteractabilityLockedReplicated = True
        cal.on_post(self.pc, args_cash)
        self.assertIsNone(cal.calibrated)

    def test_calibrated_collection_exactly_once_and_rarity_filter(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal)
        self.assertIsNotNone(cal.calibrated)
        self.assertEqual(cal.calibrated[1], 'Primary')

        common = self.make_pickup('Gear_Common', kind='gear', color=self.PALETTE[4][1], item_id='id_common', dist=100.0)
        legendary = self.make_pickup('Gear_Leg', kind='gear', color=self.HIGH_GEAR_COLORS[0], item_id='id_leg', dist=250.0)
        dup_item = self.make_pickup('Gear_Leg_Dup', kind='gear', color=self.HIGH_GEAR_COLORS[0], item_id='id_leg', dist=300.0)
        self.pickups = [common, legendary, dup_item]

        col = self.collector(cal, high_only=True)
        self.assertTrue(col.begin())
        self.assertTrue(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)
        self.assertIs(self.dispatches[0][0], legendary)
        self.assertIs(self.dispatches[0][1], self.primary)
        self.assertFalse(self.dispatches[0][2])
        self.assertEqual(col.collected_count, 1)

        # Next tick: common filtered out, legendary locked/attempted, dup_item deduplicated by item_id
        self.time += 1.0
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)

    def test_backpack_full_pauses_without_overflow(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal)
        # Fill backpack to capacity (5)
        while len(self.bp_items.items) < 5:
            self.bp_items.items.append('filler')
        g = self.make_pickup('Gear_Full', kind='gear', item_id='id_full', dist=100.0)
        self.pickups = [g]
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertEqual(len(self.dispatches), 0)
        # Free one slot -> collects cleanly
        self.bp_items.items.pop()
        self.time += 1.0
        self.assertTrue(col.tick(True))
        self.assertEqual(len(self.dispatches), 1)

    def test_accidental_equip_triggers_fault_and_halts(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal)
        g = self.make_pickup('Gear_BadEquip', kind='gear', item_id='id_eq', dist=100.0)
        self.pickups = [g]
        self.equip_on_use = True
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(True))
        self.assertTrue(col.fault)
        self.assertIsNone(col.record)

    def test_permission_loss_stops_collector(self):
        cal = self.calibrator()
        self.calibrate_manual_tap(cal)
        col = self.collector(cal)
        self.assertTrue(col.begin())
        self.assertFalse(col.tick(False))
        self.assertIsNone(col.record)


if __name__ == '__main__':
    unittest.main()
