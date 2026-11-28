"""Calibrated opt-in automatic equipment pickup via OakPlayerController.ServerUseObject.

Independent implementation using pinned historical SDK declarations
(F100rwater/borderlands4_SDK_Dumper7 a958797d4dc51ff56ec0891db0039591abb58a9a):
- OakPlayerController.ServerUseObject(Usable, UseType, bWasHeld)
- GbxGame.EUsabilityType (Primary=0, Secondary=1, Any=2)
- GbxGame.InventoryPickup.UsableActorState (FUsableActorState.bInteractabilityLockedReplicated)
- OakPlayerState.BackpackItems / BackpackContainer via inventory_capacity.inspect

Never guesses interaction semantics: requires a live witnessed manual tap pickup
that increases backpack slot count by +1 without changing equipped weapon slots.
Never calls ServerUseJunkObject, never passes bWasHeld=True, never equips, sells,
destroys or duplicates equipment, and pauses when backpack capacity is full.
"""
from collections import deque
import math
from .double_jump import struct
from .gameplay_fields import identity
from .health_pulse import enum_name
from .inventory_capacity import inspect as inspect_backpack
from .loot_vacuum import HIGH_GEAR_COLORS, PICKUP, color_kind
from .weapon_rates import prop, slot_entries

USE_OBJECT_PATH = '/Script/OakGame.OakPlayerController:ServerUseObject'
PC_CLASS = '/Script/OakGame.OakPlayerController'
USABILITY_ENUM = '/Script/GbxGame.EUsabilityType'
USABLE_STATE = '/Script/GbxGame.UsableActorState'
USE_OBJECT_SIG = (
    ('Usable', 'ZObjectProperty'),
    ('UseType', 'ZEnumProperty'),
    ('bWasHeld', 'ZBoolProperty'),
)
ALLOWED_USE_TYPES = frozenset(('Primary', 'Secondary'))


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


def equipped_signature(pawn):
    """Immutable snapshot of equipped weapon identities to prove no accidental equip."""
    entries = slot_entries(pawn)
    return tuple(identity(s.Weapon) if s.Weapon is not None else None for s in entries)


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


class ManualPickupCalibrator:
    """Read-only observer of normal manual ServerUseObject pickups.

    Never alters, blocks or replays a manual pickup. Calibrates (UseType, False)
    only after observing a local tap pickup of an ordinary gear InventoryPickup
    that increases backpack slot count by +1 with zero change to equipped slots.
    """

    def __init__(self, context, weak, classify_pickup, thread, report):
        self.context = context
        self.weak = weak
        self.classify_pickup = classify_pickup
        self.thread = thread
        self.report = report
        self.pending = None
        self.calibrated = None
        self.calibrated_scope = None

    def reset(self):
        self.pending = None
        self.calibrated = None
        self.calibrated_scope = None

    def on_pre(self, obj, args):
        try:
            pc, pawn, state, ok = self.context()
            if (ok is not True or pc.Class._path_name() != PC_CLASS
                    or identity(obj) != identity(pc)
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                return
            if getattr(args, 'bWasHeld', None) is not False:
                return
            use_type = getattr(args, 'UseType', None)
            use_name = enum_name(use_type)
            if use_name not in ALLOWED_USE_TYPES:
                return
            usable = getattr(args, 'Usable', None)
            if not pickup_interactable(usable):
                return
            kind = self.classify_pickup(usable)
            if kind != 'gear':
                return
            _, _, _, _, capacity, _, count_before = inspect_backpack(pc, pawn, 'backpack_capacity')
            if count_before >= capacity:
                return
            eq_before = equipped_signature(pawn)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.weak(usable),
                identity(usable),
                use_type,
                use_name,
                count_before,
                eq_before,
            )
        except Exception:
            self.pending = None

    def on_post(self, obj, args):
        if self.pending is None:
            return
        pending = self.pending
        self.pending = None
        try:
            scope_ids, tid, ref, usable_id, use_type, use_name, count_before, eq_before = pending
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids
                    or identity(obj) != scope_ids[0]):
                return
            eq_after = equipped_signature(pawn)
            if eq_after != eq_before:
                self.report('CALIBRATE REJECT: manual pickup altered equipped slots; ignoring')
                return
            _, _, _, _, _, _, count_after = inspect_backpack(pc, pawn, 'backpack_capacity')
            if count_after != count_before + 1:
                return
            target = ref()
            gone_or_locked = target is None or identity(target) != usable_id or not pickup_interactable(target)
            if not gone_or_locked:
                return
            self.calibrated = (use_type, use_name)
            self.calibrated_scope = scope_ids
            self.report(f'CALIBRATED: ordinary gear pickup witnessed (UseType={use_name}, bWasHeld=False)')
        except Exception:
            return


class GearPickupCollector:
    """Bounded opt-in automatic equipment collector using calibrated ServerUseObject."""

    def __init__(
        self,
        context,
        weak,
        use_fn,
        calibrator,
        scan_pickups,
        classify_pickup,
        read_color,
        item_id_reader,
        distance_fn,
        clock,
        thread,
        report,
        *,
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
        self.read_color = read_color
        self.item_id_reader = item_id_reader
        self.distance_fn = distance_fn
        self.clock = clock
        self.thread = thread
        self.report = report
        self.radius = float(radius)
        self.high_only = bool(high_only)
        self.interval = float(interval)
        self.max_per_window = int(max_per_window)
        self.record = None
        self.fault = False
        self.busy = False
        self.attempted_actors = set()
        self.attempted_items = set()
        self.recent = deque()
        self.collected_count = 0
        self.full_paused = False

    def begin(self):
        if self.record is not None or self.fault or self.busy:
            return False
        try:
            if self.calibrator.calibrated is None:
                raise ValueError('pick up one ordinary gear item manually to calibrate ServerUseObject')
            pc, pawn, state, ok = self.context()
            if (ok is not True or pc.Class._path_name() != PC_CLASS
                    or 'Default__' in pc._path_name()
                    or getattr(pc, 'HasAuthority', lambda: False)() is not True):
                raise ValueError('eligible authoritative local session required')
            scope_ids = (identity(pc), identity(pawn), identity(state))
            if self.calibrator.calibrated_scope != scope_ids:
                raise ValueError('manual pickup calibration belongs to another session')
            bound = pc.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                raise ValueError('bound ServerUseObject mismatch')
            _, _, _, _, capacity, _, count = inspect_backpack(pc, pawn, 'backpack_capacity')
            if count > capacity:
                raise ValueError('backpack exceeds capacity')
            now = self.clock()
            self.record = (
                tuple(self.weak(o) for o in (pc, pawn, state)),
                scope_ids,
                self.thread(),
                now,
            )
            self.full_paused = count >= capacity
            self.report('EXPERIMENT: calibrated automatic gear pickup armed (bWasHeld=False; capacity & rarity guarded)')
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
        if not permitted or self.thread() != tid:
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
            if self.calibrator.calibrated is None or self.calibrator.calibrated_scope != scope_ids:
                self.stop('manual pickup calibration lost')
                return False
            self.record = (refs, scope_ids, tid, now + self.interval)
            _, _, _, _, capacity, _, count_before = inspect_backpack(pc, pawn, 'backpack_capacity')
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
            candidate = self._select_candidate(pawn)
            if candidate is None:
                return False
            actor, actor_id, item_id = candidate
            use_type, use_name = self.calibrator.calibrated
            if use_name not in ALLOWED_USE_TYPES:
                self.stop('invalid calibrated interaction type')
                return False
            eq_before = equipped_signature(pawn)
            bound = pc.ServerUseObject
            if identity(bound.func) != identity(self.use_fn) or bound.func._path_name() != USE_OBJECT_PATH:
                self.stop('bound ServerUseObject changed')
                return False
            # Mark attempted BEFORE dispatch: strictly exactly-once, never retry/duplicate.
            self.attempted_actors.add(actor_id)
            if item_id is not None:
                self.attempted_items.add(item_id)
            self.recent.append(now)
            bound(actor, use_type, False)
            eq_after = equipped_signature(pawn)
            if eq_after != eq_before:
                self.fault = True
                self.record = None
                self.report('FAULT: auto gear pickup altered equipped slots; disabled for session')
                return False
            _, _, _, _, _, _, count_after = inspect_backpack(pc, pawn, 'backpack_capacity')
            if count_after == count_before + 1:
                self.collected_count += 1
            return True
        except Exception as exc:
            self.stop(str(exc)[:140])
            return False
        finally:
            self.busy = False

    def _select_candidate(self, pawn):
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
                if self.high_only:
                    color = self.read_color(actor)
                    if color_kind(color) != 'gear' or not gear_color_allowed(color, True):
                        continue
                item_id = self.item_id_reader(actor) if self.item_id_reader is not None else None
                if item_id is not None and item_id in self.attempted_items:
                    continue
                dist = self.distance_fn(pawn, actor)
                if type(dist) not in (int, float) or not math.isfinite(dist) or not 0.0 <= dist <= self.radius:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, actor, actor_id, item_id)
            except Exception:
                continue
        return None if best is None else best[1:]
