"""Isolated one-shot cash readback trial. Preparation only; not gameplay-approved.
Adapted from BL4 R11 R4 and ad326d4826ce3c44e33738290a711b3f7cef2ba7.
No automatic activation, reward grants, save edits, or XP paths.
"""
import hashlib
import sys
import threading
import time
from mods_base import build_mod

CONFIRM = 'DISPOSABLE OFFLINE CASH READBACK ONLY'
PATH = '/Script/Engine.CameraModifier:BlueprintModifyCamera'
HOOK = 'bl4_custom_isolated_cash_readback_001'
LATCH = '_bl4_custom_cash_readback_attempt_001'
ATTR = 'Att_PickupCash_Multiplier'
LIB = '/Script/GbxEngine.GbxAttributeBlueprintLibrary'
GET = (('AttributeDef', 'ZNameProperty'), ('ContextSource', 'ZObjectProperty'),
       ('DefaultValue', 'ZFloatProperty'), ('ReturnValue', 'ZFloatProperty'))
ADD = (('attribute', 'ZGbxDefPtrProperty'), ('ContextSource', 'ZObjectProperty'),
       ('ModifierType', 'ZEnumProperty'), ('modifiervalue', 'ZFloatProperty'),
       ('bAutoRefresh', 'ZBoolProperty'), ('ModifierActionResult', 'ZEnumProperty'),
       ('ReturnValue', 'ZStructProperty'))
FOUNDATION = {
    'bl4_custom_foundation': '79c569614de48f5710b2acae85b29000a596a5e80f6ac7d6ff61e71eddd28bee',
    'bl4_custom_foundation.gameplay_fields': '4571f7a654345d9dad3acefca9f28f6da2196c08598457510abd1778144cf4a7',
    'bl4_custom_foundation.session_control': '34d119f8c6abc66c2acdf851c6e8800a587548d342b6ed42568a3e745622b459',
    'bl4_custom_foundation.ground_speed': '92f02d1e8b9a42d34f34732ec5f77587dbc82e366a9c5b42737cd36179814ffb',
}
_pending = None


def report(message):
    print('[BL4 CASH READBACK] ' + message)


def identity(obj):
    token = obj._get_address()
    if type(token) is not int or token <= 0:
        raise ValueError('identity unavailable')
    return token


def gear_stamp(pawn):
    slots = pawn.EquippedInventorySlots.items
    if not 1 <= len(slots) <= 64:
        raise ValueError('gear snapshot unavailable')
    result = []
    for i in range(len(slots)):
        slot = slots[i]
        stamp = (slot.SourceItemHandle.Handle, slot.ReplicationID, slot.ReplicationKey)
        if any(type(v) is not int or not -(2**31) <= v < 2**31 for v in stamp):
            raise ValueError('invalid gear snapshot')
        result.append(stamp)
    return tuple(result)


def exact_foundation():
    for name, expected in FOUNDATION.items():
        module = sys.modules.get(name)
        if module is None or hashlib.sha256(module.__loader__.get_data(module.__file__)).hexdigest() != expected:
            raise ValueError('exact R10 source not available: ' + name)
    return sys.modules['bl4_custom_foundation']


def idle(f):
    c = f._controller
    return (mod.is_enabled is True and f.mod.is_enabled is True
            and f.auto_master.value is False and not f._auto_owned
            and f._activation_request is None and f._auto_ground is None
            and not f.conflicting_mods()
            and (c is None or not (c.records or c.fault or c.busy or c.stop_pending is not None)))


class NativeCash:
    def __init__(self, sdk):
        cls = sdk.find_class(LIB)
        self.library = cls.ClassDefaultObject
        for name, signature in (('GetValueOfAttribute', GET), ('AddModifierToGbxAttribute', ADD)):
            fn = cls._find(name)
            actual = tuple((str(p.Name), type(p).__name__) for p in fn._properties())
            if fn._path_name() != LIB + ':' + name or fn.NumParams != len(signature) or actual != signature:
                raise ValueError('native signature mismatch')
            bound = getattr(self.library, name)
            if bound.func._path_name() != fn._path_name() or identity(bound.object) != identity(self.library):
                raise ValueError('native bound function mismatch')
        self.kind = cls._find('AddModifierToGbxAttribute')._find('attribute').Struct
        if self.kind is None or str(self.kind.Name) != 'GbxAttributeDef':
            raise ValueError('typed definition required')
        self.pointer = sdk.unreal.FGbxDefPtr
        self.postadd = sdk.find_enum('EGbxAttributeModifierType').PostAdd
        outcome = sdk.find_enum('EGbxAttributeModifierActionExecOutput')
        self.failure, self.success = outcome.Failure, outcome.Success
        if (int(self.postadd), int(self.success), int(self.failure)) != (2, 0, 1):
            raise ValueError('enum mismatch')

    def read(self, pawn):
        value = self.library.GetValueOfAttribute(ATTR, pawn, -123456.0)
        if type(value) not in (int, float) or value not in (1.0, 2.0):
            raise ValueError('cash attribute not exact 1 or 2')
        return float(value)

    def add(self, pawn, delta):
        if delta not in (1.0, -1.0):
            raise ValueError('invalid trial delta')
        result = self.library.AddModifierToGbxAttribute(
            self.pointer(ATTR, self.kind), pawn, self.postadd, delta, True, self.failure)
        if type(result) is not tuple or len(result) != 3:
            raise ValueError('ambiguous native result shape')
        handle, definition, outcome = result
        if (type(outcome) is not type(self.success) or outcome != self.success
                or str(getattr(getattr(handle, '_type', None), 'Name', '')) != 'GbxAttributeModifierHandle'
                or not isinstance(definition, self.pointer)
                or str(definition._name).casefold() != ATTR.casefold()
                or definition._type is None or identity(definition._type) != identity(self.kind)
                or identity(definition) <= 0):
            raise ValueError('ambiguous native result identity/outcome')
        # Never retain the opaque handle or write to the shared definition.


def run_in_callback(f, sdk, camera, thread):
    session = f.bound_session(sdk)

    def context():
        if threading.get_ident() != thread or not idle(f):
            raise ValueError('idle original game thread required')
        pc, pawn, state, eligible = f.current_session(session)
        if eligible is not True or session[0](pawn) is not True:
            raise ValueError('strict standalone eligibility required')
        manager = pc.PlayerCameraManager
        if identity(camera.CameraOwner) != identity(manager) or identity(manager.PCOwner) != identity(pc):
            raise ValueError('local camera ownership unverified')
        return pc, pawn, state, getattr(pc, 'PlayerState')

    original = context()
    tokens = tuple(identity(obj) for obj in original)
    refs = tuple(sdk.unreal.WeakPointer(obj) for obj in original)
    stamp = gear_stamp(original[1])

    def same():
        objects = context()
        if any(ref() is None or identity(ref()) != token or identity(obj) != token
               for ref, token, obj in zip(refs, tokens, objects, strict=True)):
            raise ValueError('original session identity lost')
        if gear_stamp(objects[1]) != stamp:
            raise ValueError('gear changed')
        return objects[1]

    native = NativeCash(sdk)
    baseline = native.read(same())
    report('baseline=' + repr(baseline))
    if baseline != 1.0:
        raise ValueError('exact unit baseline required')
    report('attempt +1 PostAdd (cash only)')
    native.add(same(), 1.0)
    active = native.read(same())
    report('active=' + repr(active))
    if active != 2.0:
        raise ValueError('activation readback mismatch')
    report('attempt -1 PostAdd (same callback)')
    native.add(same(), -1.0)
    restored = native.read(same())
    report('cancelled=' + repr(restored))
    if restored != 1.0:
        raise ValueError('inverse readback mismatch')
    report('NET READBACK PASS 1.0 -> 2.0 -> 1.0; EXIT GAME NOW. Not native removal proof.')


def camera_callback(obj, _args, _ret, func):
    global _pending
    if _pending is None:
        return None
    f, sdk, thread, deadline = _pending
    if threading.get_ident() != thread or time.monotonic() > deadline:
        _pending = None
        report('HOLD: expired or wrong thread; exit game, no retry')
        return None
    try:
        if func._path_name() != PATH or not idle(f):
            raise ValueError('callback admission failed')
        # Non-local camera callbacks are not trial entrypoints.
        pc = sys.modules['mods_base'].get_pc(possibly_loading=True)
        if pc is None or identity(obj.CameraOwner) != identity(pc.PlayerCameraManager):
            return None
        _pending = None  # consume before any mutation; recursive callbacks inert
        hooks = sdk.hooks
        if (not f._monitor_registered or f._monitor_thread != thread
                or time.monotonic() - f._monitor_seen > 2.0
                or hooks.has_hook(PATH, hooks.Type.POST_UNCONDITIONAL, f._MONITOR_ID) is not True
                or hooks.has_hook(PATH, hooks.Type.POST_UNCONDITIONAL, HOOK) is not True):
            raise ValueError('verified camera monitor unavailable')
        run_in_callback(f, sdk, obj, thread)
    except Exception as exc:
        _pending = None
        report('HOLD/FAULT: ' + type(exc).__name__ + ': ' + str(exc)[:160] + '; EXIT GAME NOW; no retry')
    return None  # never block or override game callback


def arm(confirmation):
    """Explicit console invocation only; owner prerequisite attestation, not proof."""
    global _pending
    if confirmation != CONFIRM or getattr(sys, LATCH, False) is not False:
        report('REFUSED: confirmation or process latch')
        return False
    setattr(sys, LATCH, True)  # survives module reload in the same interpreter
    try:
        f = exact_foundation()
        sdk = sys.modules['unrealsdk']
        if not idle(f) or not f.ensure_monitor():
            raise ValueError('idle R10 monitor required')
        hooks = sdk.hooks
        kind = hooks.Type.POST_UNCONDITIONAL
        if hooks.has_hook(PATH, kind, HOOK) is not False:
            raise ValueError('duplicate trial hook')
        result = hooks.add_hook(PATH, kind, HOOK, camera_callback)
        if type(result) is not bool or hooks.has_hook(PATH, kind, HOOK) is not True:
            raise ValueError('trial hook registration unverified')
        _pending = (f, sdk, threading.get_ident(), time.monotonic() + 3.0)
        report('ARMED once; stay in place; exit game after result')
        return True
    except Exception as exc:
        _pending = None
        report('HOLD: ' + type(exc).__name__ + ': ' + str(exc)[:160] + '; exit game, no retry')
        return False


def disabled():
    global _pending
    _pending = None  # leave any registered callback inert until process exit


mod = build_mod(options=[], hooks=[], commands=[], keybinds=[], auto_enable=False,
                on_disable=disabled)
