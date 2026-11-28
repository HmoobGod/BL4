"""Calibrated opt-in automatic equipment pickup via OakPlayerController.ServerUseObject.

Independent implementation grounded in pinned historical SDK declarations
(F100rwater/borderlands4_SDK_Dumper7 a958797d4dc51ff56ec0891db0039591abb58a9a):
- OakPlayerController.ServerUseObject(Usable, UseType, bWasHeld)
- GbxGame.EUsabilityType (Primary=0, Secondary=1, Any=2)
- GbxGame.InventoryPickup.UsableActorState (FUsableActorState.bInteractabilityLockedReplicated)
- OakCharacter.EquippedInventorySlots (FEquippedInventorySlotsContainer -> FEquippedInventorySlot)
- OakPlayerState.BackpackItems (FGbxItemSlotsContainer -> FGbxItemContainerSlot -> FInventoryItem)
- FInventoryItem.item (FGbxItem -> FGbxItemData.InstanceId, FGbxItemState.Quantity, GbxGame_structs.hpp:16331)

Safeguards:
- Exact ground-to-backpack (InstanceId, Quantity) matching reusing loot_vacuum.native_gear_identity
- Verifies all preexisting backpack entries remain strictly unchanged
- Verifies ALL equipped categories remain unchanged (EquippedInventorySlots + ActiveWeapons.Slots)
- Per-category bounded calibration (max_age=300s), matched PRE/POST, stale-pending/reentrancy/self-calibration guards
- Fresh classification, category, rarity, distance, capacity, target identity, and permission checks immediately before dispatch
- Handles delayed asynchronous native acquisition receipts without duplicate requests; stops on timeout/uncertainty
- Yields to active Loot Vacuum gear relocation to prevent contention
"""
from collections import deque
import math
from .double_jump import struct
from .gameplay_fields import identity
from .health_pulse import enum_name
from .inventory_capacity import inspect as inspect_backpack
from .loot_vacuum import (
    DLC_GEAR_FAMILIES,
    HIGH_GEAR_COLORS,
    PICKUP,
    color_kind,
    native_gear_identity, active, level, location, distance, pickup_body_witness, classify,
)
from .weapon_rates import prop, slot_entries

USE_OBJECT_PATH = '/Script/OakGame.OakPlayerController:ServerUseObject'
PC_CLASS = '/Script/OakGame.OakPlayerController'
USABILITY_ENUM = '/Script/GbxGame.EUsabilityType'
USABLE_STATE = '/Script/GbxGame.UsableActorState'
EQUIPPED_CONTAINER = '/Script/OakGame.EquippedInventorySlotsContainer'
EQUIPPED_SLOT = '/Script/OakGame.EquippedInventorySlot'
ITEM_STRUCT = '/Script/GbxGame.InventoryItem'
HANDLE_STRUCT = '/Script/GbxGame.InventoryItemHandle'
GBX_ITEM_STRUCT = '/Script/GbxGame.GbxItem'
GBX_ITEM_DATA = '/Script/GbxGame.GbxItemData'
GBX_ITEM_STATE = '/Script/GbxGame.GbxItemState'
USE_OBJECT_SIG = (
    ('Usable', 'ZObjectProperty'),
    ('UseType', 'ZEnumProperty'),
    ('bWasHeld', 'ZBoolProperty'),
)
ALLOWED_USE_TYPES = frozenset(('Primary', 'Secondary'))
EQUIPMENT_CATEGORIES = DLC_GEAR_FAMILIES


def bind_use_object(functions, existing):
    matches = [f for f in functions if f._path_name() == USE_OBJECT_PATH]
    if len(matches) != 1:
        raise ValueError('ServerUseObject missing or ambiguous')
    fn = matches[0]
    ps = tuple(fn._properties())
    if (fn.Outer._path_name() != PC_CLASS or fn.NumParams != len(USE_OBJECT_SIG)
            or tuple((str(p.Name), type(p).__name__) for p in ps) != USE_OBJECT_SIG
            or any(p.ArrayDim != 1 for p in ps)
            or ps[0].PropertyClass._path_name() != '/Script/CoreUObject.Object'
            or ps[1].Enum._path_name() != USABILITY_ENUM):
        raise ValueError('ServerUseObject signature mismatch')
    return existing(functions, USE_OBJECT_PATH, USE_OBJECT_SIG), fn


def _handle_value(handle_obj):
    if handle_obj is None or handle_obj._type._path_name() != HANDLE_STRUCT:
        raise ValueError('unexpected FInventoryItemHandle wrapper')
    prop(handle_obj._type, 'Handle', 'ZIntProperty')
    val = handle_obj.Handle
    if type(val) is not int:
        raise ValueError('invalid FInventoryItemHandle integer')
    return val


def gbx_item_identity(owner):
    """Extract (InstanceId, Quantity) from an owner exposing FGbxItem `item` (e.g. FInventoryItem)."""
    item = struct(owner, 'item', GBX_ITEM_STRUCT)
    data = struct(item, 'data', GBX_ITEM_DATA)
    state = struct(item, 'State', GBX_ITEM_STATE)
    prop(data._type, 'InstanceId', 'ZUInt32Property')
    prop(state._type, 'Quantity', 'ZUInt32Property')
    instance, quantity = data.InstanceId, state.Quantity
    if (type(instance) is not int or type(quantity) is not int
            or not 0 <= instance <= 0xffffffff or not 0 <= quantity <= 0xffffffff):
        raise ValueError('invalid FGbxItem identity')
    if instance == 0 or quantity == 0:
        raise ValueError('empty FGbxItem identity')
    return instance, quantity


def ground_gear_identity(actor):
    """Strict non-None (InstanceId, Quantity) from ground AInventoryPickup via native_gear_identity."""
    ident = native_gear_identity(actor)
    if ident is None or len(ident) != 2 or ident[0] <= 0 or ident[1] <= 0:
        return None
    return ident


def backpack_slot_entries(pc, pawn):
    """Return (capacity, count, {handle: (equip_slot, instance_id, quantity)}) from typed backpack slots."""
    _, _, _, slots, capacity, _, count = inspect_backpack(pc, pawn, 'backpack_capacity')
    entries = {}
    for entry in slots.items:
        inv = struct(entry, 'InventoryItem', ITEM_STRUCT)
        h = _handle_value(struct(inv, 'Handle', HANDLE_STRUCT))
        prop(inv._type, 'EquipSlot', 'ZInt8Property')
        eq_slot = inv.EquipSlot
        if type(eq_slot) is not int or not -128 <= eq_slot <= 127:
            raise ValueError('invalid FInventoryItem.EquipSlot')
        inst_id, qty = gbx_item_identity(inv)
        if h in entries:
            raise ValueError('duplicate backpack item handle')
        entries[h] = (eq_slot, inst_id, qty)
    if len({v[1] for v in entries.values()}) != len(entries):
        raise ValueError('duplicate backpack instance identity')
    if len(entries) != count:
        raise ValueError('backpack slot count mismatch')
    return capacity, count, entries


def all_equipped_signature(pawn):
    """Immutable snapshot of ALL equipped categories (EquippedInventorySlots + ActiveWeapons.Slots)."""
    eq_cont = struct(pawn, 'EquippedInventorySlots', EQUIPPED_CONTAINER)
    desc = prop(eq_cont._type, 'items', 'ZArrayProperty')
    inner = desc.Inner
    if type(inner).__name__ != 'ZStructProperty' or inner.Struct._path_name() != EQUIPPED_SLOT:
        raise ValueError('unexpected EquippedInventorySlots array schema')
    eq_rows = []
    for slot in eq_cont.items:
        if slot._type._path_name() != EQUIPPED_SLOT or identity(slot._type) != identity(inner.Struct):
            raise ValueError('unexpected EquippedInventorySlot wrapper')
        src_h = _handle_value(struct(slot, 'SourceItemHandle', HANDLE_STRUCT))
        prop(slot._type, 'bLocked', 'ZBoolProperty')
        locked = slot.bLocked
        if type(locked) is not bool:
            raise ValueError('invalid EquippedInventorySlot.bLocked')
        inst = getattr(slot, 'InstancedInventory', None)
        inst_id = identity(inst) if inst is not None else None
        eq_rows.append((src_h, inst_id, locked))
    entries = slot_entries(pawn)
    weapon_rows = tuple(
        (
            identity(s.Weapon) if s.Weapon is not None else None,
            identity(s.PendingWeapon) if s.PendingWeapon is not None else None,
            identity(s.ClientPredictedPendingWeapon) if s.ClientPredictedPendingWeapon is not None else None,
        )
        for s in entries
    )
    return tuple(eq_rows), weapon_rows


def pickup_interactable(actor):
    """True only when actor is a live unlocked InventoryPickup instance."""
    if actor is None or actor.Class._path_name() != PICKUP or 'Default__' in actor._path_name():
        return False
    state = struct(actor, 'UsableActorState', USABLE_STATE)
    prop(state._type, 'bInteractabilityLockedReplicated', 'ZBoolProperty')
    return state.bInteractabilityLockedReplicated is False


def gear_color_allowed(color, high_only):
    if not high_only:
        return True
    if color is None or len(color) != 4 or not all(type(v) in (int, float) and math.isfinite(v) for v in color):
        return False
    return any(max(abs(a - b) for a, b in zip(color, ref)) <= .00002 for ref in HIGH_GEAR_COLORS)



def collection_witness(pc, pawn, actor, find):
    """Local loose gear only; same exact typed body and no dynamic interaction override."""
    if (not active(pawn) or enum_name(pawn.HealthCondition) != 'Healthy'
            or not active(actor) or level(actor) != level(pawn)
            or actor.HasAuthority() is not True or actor.Owner is not None
            or actor.RootPrimitiveComponent is None
            or identity(actor.RootPrimitiveComponent.Outer) != identity(actor)
            or not pickup_interactable(actor) or classify(actor) != 'gear'):
        return None
    body = pickup_body_witness(actor)
    if len(body) != 4:
        return None
    st = struct(actor, 'UsableActorState', USABLE_STATE)
    d = prop(st._type, 'ReplicatedDynamicInteractions', 'ZArrayProperty')
    if (type(d.Inner).__name__ != 'ZStructProperty'
            or d.Inner.Struct._path_name() != '/Script/GbxGame.DynamicUsabilityInteractionInfo'
            or len(st.ReplicatedDynamicInteractions) != 0):
        return None
    origin, target = location(pawn), location(actor)
    machines = find('OakVendingMachine', exact=False)
    if len(machines) > 256:
        return None
    for m in machines:
        if m is None or 'Default__' in m._path_name() or m.IsActorBeingDestroyed() is True:
            continue
        if level(m) != level(pawn):
            continue
        pos = location(m)
        item = m.GetIOTDForPlayer(pc)
        if (item is not None and identity(item) == identity(actor)) or min(distance(origin,pos),distance(target,pos)) <= 500**2:
            return None
    return (level(pawn), body)

def exact_ground_to_backpack_addition(before_entries, after_entries, expected_identity):
    """Return newly added handle ONLY if every prior entry is unchanged and the single
    new entry is unequipped (EquipSlot < 0) with exact (InstanceId, Quantity) match.
    """
    if any(v[1] == expected_identity[0] for v in before_entries.values()):
        return None
    for h, val in before_entries.items():
        if after_entries.get(h) != val:
            return None
    added = set(after_entries) - set(before_entries)
    if len(added) != 1:
        return None
    new_handle = next(iter(added))
    eq_slot, inst_id, qty = after_entries[new_handle]
    if eq_slot >= 0 or (inst_id, qty) != expected_identity:
        return None
    return new_handle


class ManualPickupCalibrator:
    """Read-only observer of normal manual ServerUseObject pickups.

    Calibrates per equipment category with bounded lifetime ONLY after proving
    exact ground-to-backpack (InstanceId, Quantity) acquisition with all prior
    backpack entries and all equipped categories strictly unchanged.
    """

    def __init__(
        self,
        context,
        weak,
        classify_pickup,
        category_of,
        clock,
        thread,
        report,
        *,
        witness, distance_fn,
        item_id_reader=ground_gear_identity,
        max_age=300.0,
        max_call_elapsed=2.0,
    ):
        self.context = context
        self.weak = weak
        self.classify_pickup = classify_pickup
        self.category_of = category_of
        self.item_id_reader = item_id_reader
        self.witness, self.distance_fn = witness, distance_fn
        self.clock = clock
        self.thread = thread
        self.report = report
        self.max_age = float(max_age)
        self.max_call_elapsed = float(max_call_elapsed)
        self.pending = None
        self.calibrated_by_category = {}
        self._busy = False
        self._self_dispatching = False

    def reset(self):
        self.pending = None
        self.calibrated_by_category.clear()

    def set_self_dispatching(self, active):
        self._self_dispatching = bool(active)
        if active:
            self.pending = None

    def get_calibration(self, category, scope_ids, now, witness=None, dist=None):
        entry = self.calibrated_by_category.get(category)
        if entry is None:
            return None
        use_type, use_name, cal_scope, expires_at, body, reach = entry
        if cal_scope != scope_ids or now >= expires_at:
            self.calibrated_by_category.pop(category, None)
            return None
        if witness is not None and (witness != body or dist is None or not 0 <= dist <= reach):
            return None
        return use_type, use_name

    def on_pre(self, obj, args):
        self.pending = None
        if self._busy or self._self_dispatching:
            return
        self._busy = True
        try:
            pc, pawn, state, ok = self.context()
            if (ok is not True or pc.Class._path_name() != PC_CLASS
                    or identity(obj) != identity(pc)
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                return
            was_held = getattr(args, 'bWasHeld', None)
            if was_held is not False:
                return
            use_type = getattr(args, 'UseType', None)
            use_name = enum_name(use_type)
            if use_name not in ALLOWED_USE_TYPES:
                return
            usable = getattr(args, 'Usable', None)
            if not pickup_interactable(usable):
                return
            if self.classify_pickup(usable) != 'gear':
                return
            category = self.category_of(usable)
            if category not in EQUIPMENT_CATEGORIES:
                return
            witness = self.witness(pc, pawn, usable)
            dist = self.distance_fn(pawn, usable)
            if (witness is None or type(dist) not in (int,float) or not math.isfinite(dist) or not 0 <= dist <= 500):
                return
            self.calibrated_by_category.pop(category,None)
            ground_ident = self.item_id_reader(usable)
            if ground_ident is None:
                return
            capacity, count_before, entries_before = backpack_slot_entries(pc, pawn)
            if count_before >= capacity:
                return
            eq_before = all_equipped_signature(pawn)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.clock(),
                self.weak(usable),
                identity(usable),
                ground_ident,
                category,
                use_type,
                use_name,
                was_held,
                entries_before,
                eq_before, witness, dist,
            )
        except Exception:
            self.pending = None
        finally:
            self._busy = False

    def on_post(self, obj, args):
        if self._busy or self._self_dispatching:
            self.pending = None
            return
        pending = self.pending
        self.pending = None
        if pending is None:
            return
        self._busy = True
        try:
            (scope_ids, tid, started_at, ref, usable_id, ground_ident, category,
             use_type, use_name, was_held, entries_before, eq_before, witness, dist) = pending
            now = self.clock()
            if now < started_at or (now - started_at) > self.max_call_elapsed:
                return
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids
                    or identity(obj) != scope_ids[0]):
                return
            post_usable = getattr(args, 'Usable', None)
            post_type = getattr(args, 'UseType', None)
            post_held = getattr(args, 'bWasHeld', None)
            if (post_usable is None or identity(post_usable) != usable_id
                    or enum_name(post_type) != use_name or post_held is not was_held):
                return
            eq_after = all_equipped_signature(pawn)
            if eq_after != eq_before:
                self.report('CALIBRATE REJECT: manual pickup altered an equipped slot; ignoring')
                return
            _, _, entries_after = backpack_slot_entries(pc, pawn)
            new_handle = exact_ground_to_backpack_addition(entries_before, entries_after, ground_ident)
            if new_handle is None:
                return
            target = ref()
            gone_or_locked = target is None or (identity(target) == usable_id and not pickup_interactable(target))
            if not gone_or_locked:
                return
            self.calibrated_by_category[category] = (use_type, use_name, scope_ids, now + self.max_age, witness, dist)
            self.report(
                f'CALIBRATED: category={category} UseType={use_name} bWasHeld=False '
                f'handle={new_handle} instance={ground_ident[0]} qty={ground_ident[1]}'
            )
        except Exception:
            return
        finally:
            self._busy = False


class GearPickupCollector:
    """Bounded opt-in automatic equipment collector with exact ground-to-backpack
    identity verification and delayed asynchronous receipt handling.
    """

    def __init__(
        self,
        context,
        weak,
        use_fn,
        calibrator,
        scan_pickups,
        classify_pickup,
        category_of,
        read_color,
        distance_fn,
        clock,
        thread,
        report,
        permission,
        *,
        item_id_reader=ground_gear_identity,
        vacuum_contending=lambda: False,
        radius=1500.0,
        high_only=False,
        interval=0.35,
        max_per_window=10,
        receipt_timeout=2.0,
    ):
        self.context = context
        self.weak = weak
        self.use_fn = use_fn
        self.calibrator = calibrator
        self.scan_pickups = scan_pickups
        self.classify_pickup = classify_pickup
        self.category_of = category_of
        self.read_color = read_color
        self.item_id_reader = item_id_reader
        self.distance_fn = distance_fn
        self.clock = clock
        self.thread = thread
        self.report = report
        self.permission = permission
        self.vacuum_contending = vacuum_contending
        self.radius = float(radius)
        self.high_only = bool(high_only)
        self.interval = float(interval)
        self.max_per_window = int(max_per_window)
        self.receipt_timeout = float(receipt_timeout)
        self.record = None
        self.pending_receipt = None
        self.fault = False
        self.busy = False
        self.attempted_actors = set()
        self.attempted_items = set()
        self.collected_handles = set()
        self.recent = deque()
        self.collected_count = 0
        self.full_paused = False

    def update_preferences(self, radius, high_only):
        self.radius = float(radius)
        self.high_only = bool(high_only)

    def begin(self):
        if self.record is not None or self.fault or self.busy:
            return False
        try:
            if self.permission() is not True:
                raise ValueError('activation not permitted')
            pc, pawn, state, ok = self.context()
            if (ok is not True or pc.Class._path_name() != PC_CLASS
                    or 'Default__' in pc._path_name()
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                raise ValueError('eligible authoritative local session required')
            scope_ids = (identity(pc), identity(pawn), identity(state))
            now = self.clock()
            bound = pc.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                raise ValueError('bound ServerUseObject mismatch')
            capacity, count, _ = backpack_slot_entries(pc, pawn)
            if count > capacity:
                raise ValueError('backpack exceeds capacity')
            all_equipped_signature(pawn)
            self.record = (
                tuple(self.weak(o) for o in (pc, pawn, state)),
                scope_ids,
                self.thread(),
                now,
            )
            self.pending_receipt = None
            self.full_paused = count >= capacity
            calibrated = any(
                self.calibrator.get_calibration(cat, scope_ids, now) is not None
                for cat in EQUIPMENT_CATEGORIES
            )
            self.report(
                'EXPERIMENT: calibrated automatic gear pickup armed (exact InstanceId & equip guarded)'
                if calibrated else
                'EXPERIMENT: automatic gear pickup awaiting manual tap pickup calibration per category'
            )
            return True
        except Exception as exc:
            self.report('HOLD: auto gear pickup ' + str(exc)[:140])
            return False

    def stop(self, reason):
        if self.record is not None:
            if self.pending_receipt is not None:
                self.fault = True
                self.report('FAULT: outstanding native pickup cannot be cancelled; restart before rearming')
            self.record = None
            self.pending_receipt = None
            self.report('STOP: auto gear pickup ' + reason)

    def _check_pending_receipt(self, pc, pawn, now):
        actor_ref, actor_id, ground_ident, entries_before, eq_before, deadline = self.pending_receipt
        if now >= deadline:
            self.stop('delayed gear acquisition unconfirmed; refusing retry')
            return False
        eq_now = all_equipped_signature(pawn)
        if eq_now != eq_before:
            self.fault = True
            self.record = None
            self.pending_receipt = None
            self.report('FAULT: delayed gear pickup altered an equipped slot; disabled for session')
            return False
        _, _, entries_now = backpack_slot_entries(pc, pawn)
        new_handle = exact_ground_to_backpack_addition(entries_before, entries_now, ground_ident)
        target_now = actor_ref()
        gone_or_locked = target_now is None or (identity(target_now) == actor_id and not pickup_interactable(target_now))
        if new_handle is not None and gone_or_locked:
            self.pending_receipt = None
            self.collected_handles.add(new_handle)
            self.collected_count += 1
            return True
        return False

    def tick(self, permitted):
        if self.record is None or self.fault or self.busy:
            return False
        refs, scope_ids, tid, due = self.record
        now = self.clock()
        if not permitted or self.permission() is not True or self.thread() != tid:
            self.stop('permission or thread ended')
            return False
        if self.pending_receipt is None and now < due:
            return False
        self.busy = True
        try:
            pc, pawn, state, ok = self.context()
            if (ok is not True or (identity(pc), identity(pawn), identity(state)) != scope_ids
                    or any(r() is None or identity(r()) != i for r, i in zip(refs, scope_ids, strict=True))
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                self.stop('original local session changed')
                return False
            # Never dispatch a second request while an asynchronous receipt is pending.
            if self.pending_receipt is not None:
                return self._check_pending_receipt(pc, pawn, now)
            self.record = (refs, scope_ids, tid, now + self.interval)
            if self.vacuum_contending() is True:
                return False
            capacity, count_before, _ = backpack_slot_entries(pc, pawn)
            if count_before >= capacity:
                if not self.full_paused:
                    self.full_paused = True
                    self.report('PAUSE: auto gear pickup backpack full')
                return False
            self.full_paused = False
            while self.recent and self.recent[0] <= now - 30.0:
                self.recent.popleft()
            if len(self.recent) >= self.max_per_window:
                return False
            if len(self.attempted_items) >= 4096:
                self.stop('session identity limit reached')
                return False
            candidate = self._select_candidate(pc, pawn, scope_ids, now)
            if candidate is None:
                return False
            actor, actor_id, ground_ident, category, use_type, use_name = candidate
            actor_ref = self.weak(actor)
            # Fresh pre-dispatch revalidation of permission, calibration, classification, rarity, distance, identity & capacity.
            fresh_cal = self.calibrator.get_calibration(category, scope_ids, self.clock())
            if (self.permission() is not True or self.thread() != tid
                    or self.vacuum_contending() is True
                    or fresh_cal is None or fresh_cal[1] != use_name or use_name not in ALLOWED_USE_TYPES):
                self.stop('pre-dispatch permission or calibration changed')
                return False
            pc2, pawn2, state2, ok2 = self.context()
            if (ok2 is not True or (identity(pc2), identity(pawn2), identity(state2)) != scope_ids
                    or any(r() is None or identity(r()) != i for r, i in zip(refs, scope_ids, strict=True))
                    or getattr(pc2, 'HasAuthority', lambda: False)() is not True):
                self.stop('pre-dispatch local session changed')
                return False
            live_actor = actor_ref()
            if (live_actor is None or identity(live_actor) != actor_id
                    or not pickup_interactable(live_actor)
                    or self.classify_pickup(live_actor) != 'gear'
                    or self.category_of(live_actor) != category
                    or self.item_id_reader(live_actor) != ground_ident):
                return False
            if self.high_only:
                color = self.read_color(live_actor)
                if color_kind(color) != 'gear' or not gear_color_allowed(color, True):
                    return False
            dist_now = self.distance_fn(pawn2, live_actor)
            if type(dist_now) not in (int, float) or not math.isfinite(dist_now) or not 0.0 <= dist_now <= self.radius:
                return False
            cap_now, count_now, entries_before = backpack_slot_entries(pc2, pawn2)
            if count_now >= cap_now:
                return False
            if any(v[1] == ground_ident[0] for v in entries_before.values()):
                return False
            eq_before = all_equipped_signature(pawn2)
            witness = self.calibrator.witness(pc2,pawn2,live_actor)
            if witness is None:
                return False
            final_dist = self.distance_fn(pawn2,live_actor)
            fresh_cal = self.calibrator.get_calibration(category,scope_ids,self.clock(),witness,final_dist)
            if (fresh_cal is None or fresh_cal[1] != use_name or not 0 <= final_dist <= self.radius
                    or self.permission() is not True or self.thread() != tid or self.record is None
                    or self.vacuum_contending() is True or actor_ref() is None
                    or identity(actor_ref()) != actor_id or self.item_id_reader(live_actor) != ground_ident):
                return False
            bound = pc2.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                self.stop('bound ServerUseObject changed')
                return False
            # Mark attempted BEFORE dispatch: strictly once, never retry blindly.
            self.attempted_actors.add(actor_id)
            self.attempted_items.add(ground_ident)
            dispatch_at = self.clock()
            self.recent.append(dispatch_at)
            self.pending_receipt = (actor_ref, actor_id, ground_ident, entries_before, eq_before, dispatch_at + self.receipt_timeout)
            self.calibrator.set_self_dispatching(True)
            try:
                bound(live_actor, fresh_cal[0], False)
            finally:
                self.calibrator.set_self_dispatching(False)
            if self.record is None or self.fault:
                return False
            eq_after = all_equipped_signature(pawn2)
            if eq_after != eq_before:
                self.fault = True
                self.record = None
                self.pending_receipt = None
                self.report('FAULT: auto gear pickup altered an equipped slot; disabled for session')
                return False
            _, _, entries_after = backpack_slot_entries(pc2, pawn2)
            new_handle = exact_ground_to_backpack_addition(entries_before, entries_after, ground_ident)
            target_after = actor_ref()
            gone_or_locked = target_after is None or (identity(target_after) == actor_id and not pickup_interactable(target_after))
            if new_handle is not None and gone_or_locked and self.clock() < dispatch_at + self.receipt_timeout:
                self.pending_receipt = None
                self.collected_handles.add(new_handle)
                self.collected_count += 1
                return True
            # Handle delayed asynchronous native receipt without duplicate requests.
            self.pending_receipt = (
                actor_ref, actor_id, ground_ident, entries_before, eq_before,
                dispatch_at + self.receipt_timeout,
            )
            return False
        except Exception as exc:
            self.stop(str(exc)[:140])
            return False
        finally:
            self.busy = False

    def _select_candidate(self, pc, pawn, scope_ids, now):
        best = None
        actors = self.scan_pickups()
        if len(actors) > 1024:
            return None
        for actor in actors:
            try:
                if not pickup_interactable(actor):
                    continue
                actor_id = identity(actor)
                if actor_id in self.attempted_actors:
                    continue
                if self.classify_pickup(actor) != 'gear':
                    continue
                category = self.category_of(actor)
                if category not in EQUIPMENT_CATEGORIES:
                    continue
                cal = self.calibrator.get_calibration(category, scope_ids, now)
                if cal is None:
                    continue
                if self.high_only:
                    color = self.read_color(actor)
                    if color_kind(color) != 'gear' or not gear_color_allowed(color, True):
                        continue
                ground_ident = self.item_id_reader(actor)
                if ground_ident is None or any(v[0] == ground_ident[0] for v in self.attempted_items):
                    continue
                dist = self.distance_fn(pawn, actor)
                if type(dist) not in (int, float) or not math.isfinite(dist) or not 0.0 <= dist <= self.radius:
                    continue
                witness = self.calibrator.witness(pc,pawn,actor)
                if witness is None or self.calibrator.get_calibration(category,scope_ids,now,witness,dist) is None:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, actor, actor_id, ground_ident, category, cal[0], cal[1])
            except Exception:
                continue
        return None if best is None else best[1:]
