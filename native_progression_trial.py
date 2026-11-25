"""Source-only native PostAdd trial; deliberately not wired to F8 or hooks.
Community evidence: Kevin-hDev/Mods-Borderlands-4, Apache-2.0,
897c99eef4cd6d91637816d101456d59f4fb920f, it_follows/it_follows/normal/rewards.py.
Independent implementation. Cancellation is not removal; never re-arm a trial.
"""
import math
import struct

from bl4_custom_foundation.gameplay_fields import identity, gear_equipment_signature

ATTRIBUTES = {'xp': 'Att_CombatXP_Multiplier', 'cash': 'Att_PickupCash_Multiplier'}
LIB = '/Script/GbxEngine.GbxAttributeBlueprintLibrary'
GET = (('AttributeDef', 'ZNameProperty'), ('ContextSource', 'ZObjectProperty'),
       ('DefaultValue', 'ZFloatProperty'), ('ReturnValue', 'ZFloatProperty'))
ADD = (('attribute', 'ZGbxDefPtrProperty'), ('ContextSource', 'ZObjectProperty'),
       ('ModifierType', 'ZEnumProperty'), ('modifiervalue', 'ZFloatProperty'),
       ('bAutoRefresh', 'ZBoolProperty'), ('ModifierActionResult', 'ZEnumProperty'),
       ('ReturnValue', 'ZStructProperty'))


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class NativeAPI:
    def __init__(self, sdk):
        cls = sdk.find_class(LIB)
        library = cls.ClassDefaultObject
        for name, signature in (('GetValueOfAttribute', GET), ('AddModifierToGbxAttribute', ADD)):
            fn = cls._find(name)
            actual = tuple((str(p.Name), type(p).__name__) for p in fn._properties())
            if fn._path_name() != LIB + ':' + name or fn.NumParams != len(signature) or actual != signature:
                raise ValueError('native signature mismatch')
            if getattr(library, name).func._path_name() != fn._path_name():
                raise ValueError('bound function mismatch')
        self.kind = cls._find('AddModifierToGbxAttribute')._find('attribute').Struct
        if self.kind is None or str(self.kind.Name) != 'GbxAttributeDef':
            raise ValueError('typed definition required')
        self.pointer = sdk.unreal.FGbxDefPtr
        self.postadd = sdk.find_enum('EGbxAttributeModifierType').PostAdd
        outcome = sdk.find_enum('EGbxAttributeModifierActionExecOutput')
        self.failure, self.success = outcome.Failure, outcome.Success
        if (int(self.postadd), int(self.success), int(self.failure)) != (2, 0, 1):
            raise ValueError('enum mismatch')
        self.library = library

    def read(self, key, pawn):
        value = self.library.GetValueOfAttribute(ATTRIBUTES[key], pawn, -123456.0)
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 10:
            raise ValueError('unresolved native attribute')
        return f32(value)

    def add(self, key, pawn, delta):
        result = self.library.AddModifierToGbxAttribute(
            self.pointer(ATTRIBUTES[key], self.kind), pawn, self.postadd, delta, True, self.failure)
        # Community runtime trials: opaque return handle, resolved attribute out
        # parameter, then action outcome. SDK binding emits these in that order.
        if type(result) is not tuple or len(result) != 3:
            raise ValueError('native result shape ambiguous; restart required')
        handle, definition, outcome = result
        if type(outcome) is not type(self.success) or outcome != self.success:
            raise ValueError('native outcome ambiguous; restart required')
        if (str(getattr(getattr(handle, '_type', None), 'Name', '')) != 'GbxAttributeModifierHandle'
                or not isinstance(definition, self.pointer)
                or str(definition._name).casefold() != ATTRIBUTES[key].casefold()
                or definition._type is None or identity(definition._type) != identity(self.kind)
                or identity(definition) <= 0):
            raise ValueError('native returned identity ambiguous; restart required')
        # Do not retain or remove the opaque handle, and never write to the definition.


class Trial:
    """One feature, one activation and at most one inverse; no live slider updates.
    Caller must supply R11 Controller and explicit offline consent callback.
    No release admission: a lost context or ambiguous result requires restart.
    """
    def __init__(self, controller, api, consent, key):
        if key not in ATTRIBUTES:
            raise ValueError('unsupported reward')
        self.controller, self.api, self.consent, self.key = controller, api, consent, key
        self.status = 'unused'
        self.owner = None

    def _context(self, *, restoring=False):
        c = self.controller
        pc, pawn, state, eligible = c.context()
        if not eligible or c.fault or (not restoring and (self.consent() is not True or c.stop_pending is not None)):
            raise ValueError('eligible explicit offline session required')
        return (pc, pawn, state), gear_equipment_signature(pawn)

    def _same(self, *, restoring=False):
        c = self.controller
        objects, stamp = self._context(restoring=restoring)
        if c.thread() != self.thread or stamp != self.stamp:
            raise ValueError('thread or equipment changed')
        if any(ref() is None or identity(ref()) != token or identity(obj) != token
               for ref, token, obj in zip(self.owner, self.tokens, objects, strict=True)):
            raise ValueError('original owner lost')
        return objects[1]

    def _fault(self, exc):
        self.status = 'fault'
        self.controller.fail('native reward trial ' + self.key + ': ' + str(exc)[:120])
        return False

    def activate(self, selection):
        if self.status != 'unused':
            return False
        if type(selection) not in (int, float) or not math.isfinite(selection) or not 1.1 <= selection <= 10 or selection != round(selection, 1):
            return False
        try:
            objects, self.stamp = self._context()
            self.thread = self.controller.thread()
            self.owner = tuple(self.controller.weak_pointer(obj) for obj in objects)
            self.tokens = tuple(identity(obj) for obj in objects)
            pawn = self._same()
            if self.api.read(self.key, pawn) != 1.0:
                return False  # do not scale or adopt gear/foreign bonus
            self.delta = f32(selection - 1.0)
            self.target = f32(1.0 + self.delta)
            if not self.controller.log('NATIVE TRIAL add ' + self.key + ': ' + repr(self.delta)):
                return False
            self.status = 'uncertain'  # before call; exception may have applied it
            self.api.add(self.key, self._same(), self.delta)
            if self.api.read(self.key, self._same()) != self.target:
                raise ValueError('activation readback mismatch')
            self.status = 'active'
            return True
        except Exception as exc:
            return self._fault(exc)

    def cancel(self):
        if self.status != 'active':
            return False
        try:
            pawn = self._same(restoring=True)
            if self.api.read(self.key, pawn) != self.target:
                raise ValueError('unexpected attribute drift')
            if not self.controller.log('NATIVE TRIAL inverse ' + self.key + ': ' + repr(-self.delta)):
                raise ValueError('report unavailable')
            self.status = 'uncertain'
            self.api.add(self.key, self._same(restoring=True), -self.delta)
            if self.api.read(self.key, self._same(restoring=True)) != 1.0:
                raise ValueError('inverse readback mismatch')
            self.status = 'cancelled'  # net effect observed, not native handle cleanup
            return True
        except Exception as exc:
            return self._fault(exc)
