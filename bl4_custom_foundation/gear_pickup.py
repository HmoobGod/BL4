"""Calibrated opt-in automatic equipment pickup via OakPlayerController.ServerUseObject.

Independent implementation grounded in pinned historical SDK declarations
(F100rwater/borderlands4_SDK_Dumper7 a958797d4dc51ff56ec0891db0039591abb58a9a):
- OakPlayerController.ServerUseObject(Usable, UseType, bWasHeld)
- GbxGame.EUsabilityType (Primary=0, Secondary=1, Any=2)
- GbxGame.InventoryPickup.UsableActorState (FUsableActorState.bInteractabilityLockedReplicated)
- OakCharacter.EquippedInventorySlots (FEquippedInventorySlotsContainer -> FEquippedInventorySlot)
- OakPlayerState.BackpackItems (FGbxItemSlotsContainer -> FGbxItemContainerSlot -> FInventoryItem.Handle/EquipSlot)

Safeguards:
- Per-category calibration with bounded lifetime (never extrapolates across gear classes)
- Exact collected FInventoryItemHandle (+1 new handle, EquipSlot < 0, no lost handles)
- All equipped categories unchanged (EquippedInventorySlots + ActiveWeapons.Slots)
- Exact PRE/POST interaction matching, stale-pending clearing, reentrancy & self-calibration guards
- Fresh permission, scope, capacity, target identity, and Loot Vacuum contention checks right before dispatch
- Stops on uncertain acquisition; never retries blindly; never calls ServerUseJunkObject or bWasHeld=True
"""
from collections import deque
import math
from .double_jump import struct
from .gameplay_fields import identity
from .health_pulse import enum_name
from .inventory_capacity import inspect as inspect_backpack
from .loot_vacuum import DLC_GEAR_FAMILIES, HIGH_GEAR_COLORS, PICKUP, color_kind
from .weapon_rates import prop, slot_entries

USE_OBJECT_PATH = '/Script/OakGame.OakPlayerController:ServerUseObject'
PC_CLASS = '/Script/OakGame.OakPlayerController'
USABILITY_ENUM = '/Script/GbxGame.EUsabilityType'
USABLE_STATE = '/Script/GbxGame.UsableActorState'
EQUIPPED_CONTAINER = '/Script/OakGame.EquippedInventorySlotsContainer'
EQUIPPED_SLOT = '/Script/OakGame.EquippedInventorySlot'
ITEM_STRUCT = '/Script/GbxGame.InventoryItem'
HANDLE_STRUCT = '/Script/GbxGame.InventoryItemHandle'
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


def backpack_slot_handles(pc, pawn):
    """Return (capacity, count, {handle_int: equip_slot_int}) from exact typed backpack slots."""
    _, _, _, slots, capacity, _, count = inspect_backpack(pc, pawn, 'backpack_capacity')
    handles = {}
    for entry in slots.items:
        inv = struct(entry, 'InventoryItem', ITEM_STRUCT)
        h = _handle_value(struct(inv, 'Handle', HANDLE_STRUCT))
        prop(inv._type, 'EquipSlot', 'ZInt8Property')
        eq_slot = inv.EquipSlot
        if type(eq_slot) is not int or not -128 <= eq_slot <= 127:
            raise ValueError('invalid FInventoryItem.EquipSlot')
        if h in handles:
            raise ValueError('duplicate backpack item handle')
        handles[h] = eq_slot
    if len(handles) != count:
        raise ValueError('backpack handle count mismatch')
    return capacity, count, handles


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


def single_backpack_addition(before_handles, after_handles):
    """Return the single newly added unequipped item handle, or None if not exact +1 backpack add."""
    before_keys = set(before_handles)
    after_keys = set(after_handles)
    if not before_keys.issubset(after_keys):
        return None
    added = after_keys - before_keys
    if len(added) != 1:
        return None
    new_handle = next(iter(added))
    if after_handles[new_handle] >= 0:
        return None
    return new_handle


class ManualPickupCalibrator:
    """Read-only observer of normal manual ServerUseObject pickups.

    Calibrates per equipment category with bounded lifetime. Never alters,
    blocks, replays, or self-calibrates from collector-dispatched calls.
    """

    def __init__(
        self,
        context,
        weak,
        classify_pickup,
        category_of,
        item_id_reader,
        clock,
        thread,
        report,
        *,
        max_age=300.0,
        max_call_elapsed=2.0,
    ):
        self.context = context
        self.weak = weak
        self.classify_pickup = classify_pickup
        self.category_of = category_of
        self.item_id_reader = item_id_reader
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

    def get_calibration(self, category, scope_ids, now):
        entry = self.calibrated_by_category.get(category)
        if entry is None:
            return None
        use_type, use_name, cal_scope, expires_at = entry
        if cal_scope != scope_ids or now >= expires_at:
            self.calibrated_by_category.pop(category, None)
            return None
        return use_type, use_name

    def on_pre(self, obj, args):
        # Always clear stale pending before any early return.
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
            item_id = self.item_id_reader(usable)
            if item_id is None:
                return
            capacity, count_before, handles_before = backpack_slot_handles(pc, pawn)
            if count_before >= capacity:
                return
            eq_before = all_equipped_signature(pawn)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.clock(),
                self.weak(usable),
                identity(usable),
                item_id,
                category,
                use_type,
                use_name,
                was_held,
                handles_before,
                eq_before,
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
            (scope_ids, tid, started_at, ref, usable_id, _item_id, category,
             use_type, use_name, was_held, handles_before, eq_before) = pending
            now = self.clock()
            if now < started_at or (now - started_at) > self.max_call_elapsed:
                return
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids
                    or identity(obj) != scope_ids[0]):
                return
            # Match exact POST args to PRE call.
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
            _, _, handles_after = backpack_slot_handles(pc, pawn)
            new_handle = single_backpack_addition(handles_before, handles_after)
            if new_handle is None:
                return
            target = ref()
            gone_or_locked = target is None or identity(target) != usable_id or not pickup_interactable(target)
            if not gone_or_locked:
                return
            self.calibrated_by_category[category] = (use_type, use_name, scope_ids, now + self.max_age)
            self.report(
                f'CALIBRATED: category={category} UseType={use_name} bWasHeld=False handle={new_handle}'
            )
        except Exception:
            return
        finally:
            self._busy = False


class GearPickupCollector:
    """Bounded opt-in automatic equipment collector using per-category calibrated ServerUseObject."""

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
        item_id_reader,
        distance_fn,
        clock,
        thread,
        report,
        permission,
        *,
        vacuum_contending=lambda: False,
        radius=1500.0,
        high_only=False,
        interval=0.35,
        max_per_window=10,
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
        self.record = None
        self.fault = False
        self.busy = False
        self.attempted_actors = set()
        self.attempted_items = set()
        self.collected_handles = set()
        self.recent = deque()
        self.collected_count = 0
        self.full_paused = False

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
            has_any = any(
                self.calibrator.get_calibration(cat, scope_ids, now) is not None
                for cat in EQUIPMENT_CATEGORIES
            )
            if not has_any:
                raise ValueError('pick up one ordinary gear item manually to calibrate ServerUseObject')
            bound = pc.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                raise ValueError('bound ServerUseObject mismatch')
            capacity, count, _ = backpack_slot_handles(pc, pawn)
            if count > capacity:
                raise ValueError('backpack exceeds capacity')
            all_equipped_signature(pawn)
            self.record = (
                tuple(self.weak(o) for o in (pc, pawn, state)),
                scope_ids,
                self.thread(),
                now,
            )
            self.full_paused = count >= capacity
            self.report('EXPERIMENT: calibrated automatic gear pickup armed (per-category; exact handle & equip guarded)')
            return True
        except Exception as exc:
            self.report('HOLD: auto gear pickup ' + str(exc)[:140])
            return False

    def stop(self, reason):
        if self.record is not None:
            self.record = None
            self.report('STOP: auto gear pickup ' + reason)

    def tick(self, permitted):
        if self.record is None or self.fault or self.busy:
            return False
        refs, scope_ids, tid, due = self.record
        now = self.clock()
        if not permitted or self.permission() is not True or self.thread() != tid:
            self.stop('permission or thread ended')
            return False
        if now < due:
            return False
        self.busy = True
        try:
            pc, pawn, state, ok = self.context()
            if (ok is not True or (identity(pc), identity(pawn), identity(state)) != scope_ids
                    or any(r() is None or identity(r()) != i for r, i in zip(refs, scope_ids, strict=True))
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                self.stop('original local session changed')
                return False
            self.record = (refs, scope_ids, tid, now + self.interval)
            if self.vacuum_contending() is True:
                return False
            capacity, count_before, _ = backpack_slot_handles(pc, pawn)
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
            candidate = self._select_candidate(pawn, scope_ids, now)
            if candidate is None:
                return False
            actor, actor_id, item_id, category, use_type, use_name = candidate
            actor_ref = self.weak(actor)
            # Fresh pre-dispatch verification immediately before native call.
            if (self.permission() is not True or self.thread() != tid
                    or self.vacuum_contending() is True
                    or self.calibrator.get_calibration(category, scope_ids, self.clock()) is None
                    or use_name not in ALLOWED_USE_TYPES):
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
                    or self.item_id_reader(live_actor) != item_id):
                return False
            cap_now, count_now, handles_before = backpack_slot_handles(pc2, pawn2)
            if count_now >= cap_now:
                return False
            eq_before = all_equipped_signature(pawn2)
            bound = pc2.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                self.stop('bound ServerUseObject changed')
                return False
            # Mark attempted BEFORE dispatch: strictly once, never retry blindly.
            self.attempted_actors.add(actor_id)
            self.attempted_items.add(item_id)
            self.recent.append(self.clock())
            self.calibrator.set_self_dispatching(True)
            try:
                bound(live_actor, use_type, False)
            finally:
                self.calibrator.set_self_dispatching(False)
            eq_after = all_equipped_signature(pawn2)
            if eq_after != eq_before:
                self.fault = True
                self.record = None
                self.report('FAULT: auto gear pickup altered an equipped slot; disabled for session')
                return False
            _, _, handles_after = backpack_slot_handles(pc2, pawn2)
            new_handle = single_backpack_addition(handles_before, handles_after)
            target_after = actor_ref()
            gone_or_locked = target_after is None or identity(target_after) != actor_id or not pickup_interactable(target_after)
            if new_handle is None or not gone_or_locked:
                self.stop('uncertain gear acquisition; refusing retry')
                return False
            self.collected_handles.add(new_handle)
            self.collected_count += 1
            return True
        except Exception as exc:
            self.stop(str(exc)[:140])
            return False
        finally:
            self.busy = False

    def _select_candidate(self, pawn, scope_ids, now):
        best = None
        for actor in self.scan_pickups():
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
                item_id = self.item_id_reader(actor)
                if item_id is None or item_id in self.attempted_items:
                    continue
                dist = self.distance_fn(pawn, actor)
                if type(dist) not in (int, float) or not math.isfinite(dist) or not 0.0 <= dist <= self.radius:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, actor, actor_id, item_id, category, cal[0], cal[1])
            except Exception:
                continue
        return None if best is None else best[1:]
