"""Source-only, unregistered one-shot capacity callback. Native execution HOLD.

Reuse exact R10 session API and own cash trial BoundFunction admission pattern.
No automatic hooks, game imports, package metadata or gameplay/save access.
The caller must separately authorize a disposable native session and register
this callback on the verified game thread; this file does not register it.
"""
import hashlib
import sys
import threading
import time
from inventory_capacity import CONFIRM, FIELDS, CapacityFault, readback

PATH = '/Script/Engine.CameraModifier:BlueprintModifyCamera'
LATCH = '_bl4_custom_inventory_capacity_attempt_001'
FOUNDATION = {
    'bl4_custom_foundation': '79c569614de48f5710b2acae85b29000a596a5e80f6ac7d6ff61e71eddd28bee',
    'bl4_custom_foundation.gameplay_fields': '4571f7a654345d9dad3acefca9f28f6da2196c08598457510abd1778144cf4a7',
    'bl4_custom_foundation.session_control': '34d119f8c6abc66c2acdf851c6e8800a587548d342b6ed42568a3e745622b459',
    'bl4_custom_foundation.ground_speed': '92f02d1e8b9a42d34f34732ec5f77587dbc82e366a9c5b42737cd36179814ffb',
}
CONFLICTS = {'bl4backpacksize', 'bl4cashreadbacktrial', 'squ1ggsboostingtools',
             'bl4inventorycapacity'}


def require(ok, message):
    if ok is not True:
        raise CapacityFault(message)


def identity(obj):
    require(obj is not None, 'missing identity')
    token = obj._get_address()
    require(type(token) is int and token > 0, 'invalid identity')
    return token


def exact_foundation():
    for name, digest in FOUNDATION.items():
        module = sys.modules.get(name)
        require(module is not None and hashlib.sha256(
            module.__loader__.get_data(module.__file__)).hexdigest() == digest,
            'exact R10 source required: ' + name)
    return sys.modules['bl4_custom_foundation']


def idle(f, sdk, thread):
    require(threading.get_ident() == thread, 'wrong game thread')
    require(f.mod.is_enabled is True and f.auto_master.value is False,
            'Foundation must be enabled and persistent master OFF')
    require(not f._auto_owned and f._activation_request is None and f._auto_ground is None,
            'R10 activation pending')
    require(not f.conflicting_mods(), 'R10 mod conflict')
    for name, module in tuple(sys.modules.items()):
        if '.' not in name and name.replace('_', '').casefold() in CONFLICTS:
            require(getattr(getattr(module, 'mod', None), 'is_enabled', None) is False,
                    'inventory/cash mod conflict: ' + name)
    c = f._controller
    require(c is None or (not c.records and not c.fault and not c.busy
                          and c.stop_pending is None), 'R10 controller not idle')
    require(f._monitor_registered is True and not f._monitor_error and
            f._monitor_thread == thread and 0 <= time.monotonic() - f._monitor_seen <= 2.0,
            'verified recent R10 monitor required')
    require(sdk.hooks.has_hook(f._MONITOR_PATH, sdk.hooks.Type.POST_UNCONDITIONAL,
                               f._MONITOR_ID) is True, 'R10 monitor missing')


def property_of(owner_type, name, prop_type):
    p = owner_type._find_prop(name)
    require(str(p.Name) == name and type(p).__name__ == prop_type and p.ArrayDim == 1,
            'reflection mismatch: ' + name)
    return p


def embedded(owner_type, name, expected, wrapper):
    p = property_of(owner_type, name, 'ZStructProperty')
    require(str(p.Struct.Name) == expected and identity(p.Struct) == identity(wrapper._type),
            'embedded struct mismatch: ' + name)
    return p.Struct


def reflection_stamp(ps, kind):
    """Identity tokens only; no offsets or raw pointer operations."""
    cn, sn = FIELDS[kind]
    container, slots = getattr(ps, cn), getattr(ps, sn)
    ct = embedded(ps.Class, cn, 'GbxItemContainer', container)
    st = embedded(ps.Class, sn, 'GbxItemSlotsContainer', slots)
    capacity = container.MaxSize
    at = embedded(ct, 'MaxSize', 'GbxAttributeInteger', capacity)
    property_of(at, 'Value', 'ZIntProperty')
    property_of(at, 'BaseValue', 'ZIntProperty')
    property_of(ct, 'ProfileId', 'ZByteProperty')
    array = property_of(st, 'items', 'ZArrayProperty')
    inner = array.Inner
    require(type(inner).__name__ == 'ZStructProperty' and inner.ArrayDim == 1 and
            str(inner.Struct.Name) == 'GbxItemContainerSlot', 'slot element reflection mismatch')
    return tuple(identity(x) for x in (container, slots, capacity, ct, st, at, inner.Struct))


def occupancy_stamp(ps, kind):
    """Read-only candidate occupancy and item identity evidence.

    flameaway/bl4-fix transfer.py blob 96781a5dd1133b0f18d78ad0be3b4bd074017606
    counts backpack handles other than -1 only when EquipSlot == -1.
    Bank non-empty handle count is a conservative candidate, not certified.
    The core still requires raw slot length <= baseline; never expands that gate.
    """
    items = getattr(ps, FIELDS[kind][1]).items
    require(1 <= len(items) <= 10000, 'slot count unavailable')
    entries = []
    for i in range(len(items)):
        item = items[i].InventoryItem
        handle = item.Handle.Handle
        require(type(handle) is int and -1 <= handle < 2**31, 'invalid inventory handle')
        equipped = int(item.EquipSlot) if kind == 'backpack' else None
        require(equipped is None or -1 <= equipped <= 255, 'invalid equip slot')
        entries.append((handle, equipped))
    live = [handle for handle, _ in entries if handle != -1]
    require(len(set(live)) == len(live), 'duplicate live inventory handle')
    count = sum(h != -1 and (kind == 'bank' or e == -1) for h, e in entries)
    return count, tuple(entries)


def bound_camera(sdk, func, camera):
    require(isinstance(func, sdk.unreal.BoundFunction) and
            isinstance(func.func, sdk.unreal.UFunction) and
            func.func._path_name() == PATH and identity(func.object) == identity(camera),
            'camera BoundFunction identity mismatch')


def live_objects(f, sdk, api, camera, thread):
    idle(f, sdk, thread)
    pc, pawn, state, eligible = f.current_session(api)
    require(eligible is True and api[0](pawn) is True, 'strict standalone eligibility required')
    ps = pc.PlayerState
    require(str(ps.Class.Name) == 'OakPlayerState', 'OakPlayerState required')
    require(len(state.PlayerArray) == 1 and identity(state.PlayerArray[0]) == identity(ps),
            'sole PlayerState mismatch')
    viewport = sys.modules['mods_base'].ENGINE.GameViewport
    world = viewport.World
    require(str(world.Class.Name) == 'World' and identity(world.GameState) == identity(state),
            'active world mismatch')
    require(identity(api[4](pc)) == identity(state) and identity(api[4](pawn)) == identity(state),
            'controller/pawn game state mismatch')
    gi = world.OwningGameInstance
    require(str(gi.Class.Name) == 'OakGameInstance' and len(gi.LocalPlayers) == 1,
            'sole local player required')
    lp = gi.LocalPlayers[0]
    require(identity(lp.PlayerController) == identity(pc), 'local player controller mismatch')
    manager = pc.PlayerCameraManager
    require(identity(camera.CameraOwner) == identity(manager) and
            identity(manager.PCOwner) == identity(pc), 'local camera ownership mismatch')
    return pc, pawn, state, ps, viewport, world, gi, lp, manager, camera


class OneShot:
    """Manual source integration only. Arm consumes process latch before admission.

    Callback returns None (never overrides a game function); result is retained
    for source-level validation. Any failure is terminal for the process.
    No game hooks are installed by this class.
    """
    def __init__(self):
        self.pending = None
        self.result = None
        self.status = 'idle'

    def arm(self, kind, confirmation):
        if (confirmation != CONFIRM or kind not in FIELDS or
                getattr(sys, LATCH, False) is not False):
            return False
        setattr(sys, LATCH, True)
        self.status = 'HOLD: admission incomplete; no retry'
        try:
            f, sdk = exact_foundation(), sys.modules['unrealsdk']
            thread = threading.get_ident()
            idle(f, sdk, thread)
            self.pending = f, sdk, kind, thread, time.monotonic() + 3.0
            self.status = 'armed'
            return True
        except Exception as exc:
            self.pending = None
            self.status = 'HOLD: ' + str(exc) + '; no retry'
            return False

    def disarm(self):
        self.pending = None
        if self.status == 'armed':
            self.status = 'HOLD: disarmed; no retry'

    def callback(self, camera, _args, _ret, func):
        pending = self.pending
        if pending is None:
            return None
        f, sdk, kind, thread, deadline = pending
        # Consume before any admission or write; nested callbacks are inert.
        self.pending = None
        self.status = 'HOLD: callback incomplete; no retry'
        try:
            require(threading.get_ident() == thread and time.monotonic() <= deadline,
                    'wrong thread or expired callback')
            require(exact_foundation() is f and sys.modules.get('unrealsdk') is sdk,
                    'source/module identity changed')
            bound_camera(sdk, func, camera)
            api = f.bound_session(sdk)
            original = live_objects(f, sdk, api, camera, thread)
            tokens = tuple(identity(x) for x in original)
            weak = tuple(sdk.unreal.WeakPointer(x) for x in original)
            stamp = reflection_stamp(original[3], kind)
            occupancy = occupancy_stamp(original[3], kind)

            def same():
                require(exact_foundation() is f and sys.modules.get('unrealsdk') is sdk,
                        'source/module identity changed')
                objects = live_objects(f, sdk, api, camera, thread)
                for ref, token, obj in zip(weak, tokens, objects, strict=True):
                    require(identity(ref()) == token and identity(obj) == token,
                            'original weak identity lost')
                require(reflection_stamp(objects[3], kind) == stamp,
                        'embedded inventory identity changed')
                require(occupancy_stamp(objects[3], kind) == occupancy,
                        'inventory handle or equipment changed')
                return objects[3]

            self.result = readback(kind, CONFIRM, same)
            self.status = 'READBACK PASS; exit disposable session; not save/reload proof'
        except Exception as exc:
            self.status = 'HOLD/FAULT: ' + str(exc) + '; exit disposable session; no retry'
        return None
