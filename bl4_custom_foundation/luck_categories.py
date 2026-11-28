"""Read-only local luck category evidence, not a luck modifier.
No cached array positions, definition writes, native modifier calls or inferred units.
"""
import math
import re
from .gameplay_fields import identity
from .double_jump import struct
from .weapon_rates import prop
from .health_pulse import enum_name

PC = '/Script/OakGame.OakPlayerController'
STATE = '/Script/OakGame.LuckCategoryAttributesState'
ENTRY = '/Script/OakGame.LuckCategoryAttribute'
DEFINITION = '/Script/OakGame.LuckCategoryDef'
FLOAT = '/Script/GbxCore.GbxAttributeFloat'
CATEGORY_ENUM = '/Script/OakGame.ELuckCategoryType'
MODIFIER_ENUM = '/Script/GbxCore.EGbxAttributeModifierType'


def snapshot(pc, *, identities=False):
    if pc.Class._path_name() != PC or 'Default__' in pc._path_name():
        raise ValueError('exact local OakPlayerController required')
    state = struct(pc, 'LuckCategoryAttributesState', STATE)
    d = prop(state._type, 'LuckCategories', 'ZArrayProperty')
    inner = d.Inner
    if type(inner).__name__ != 'ZStructProperty' or inner.Struct._path_name() != ENTRY:
        raise ValueError('unexpected luck category array schema')
    arr = state.LuckCategories
    count = len(arr)
    if not 0 < count <= 128:
        raise ValueError('empty or oversized luck category array')
    rows = {}
    for entry in arr:
        if (len(rows) >= count or entry._type._path_name() != ENTRY
                or identity(entry._type) != identity(inner.Struct)):
            raise ValueError('unexpected luck entry wrapper or array changed')
        desc = prop(entry._type, 'Category', 'ZGbxDefPtrProperty')
        cat = entry.Category
        if (type(cat).__name__ != 'FGbxDefPtr' or desc.Struct._path_name() != DEFINITION
                or cat._type is None or cat._type._path_name() != DEFINITION
                or identity(cat._type) != identity(desc.Struct)):
            raise ValueError('unresolved or unexpected luck definition')
        name = cat._name
        if (type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_./:-]{1,256}', name)
                or name.casefold() == 'none' or name.casefold() in rows):
            raise ValueError('invalid or duplicate category token')
        for field, expected in (('CategoryType', CATEGORY_ENUM), ('ModifierType', MODIFIER_ENUM)):
            if prop(cat._type, field, 'ZEnumProperty').Enum._path_name() != expected:
                raise ValueError('unexpected luck definition enum')
        kind, modifier = enum_name(cat.CategoryType), enum_name(cat.ModifierType)
        if kind not in ('ModifiableAttribute', 'Formula') or not modifier or not re.fullmatch(r'[A-Za-z0-9_]{1,80}', modifier):
            raise ValueError('unrecognized luck category or modifier enum')
        value = struct(entry, 'Value', FLOAT)
        vals = []
        for field in ('Value', 'BaseValue'):
            prop(value._type, field, 'ZFloatProperty')
            v = getattr(value, field)
            if type(v) not in (float, int) or not math.isfinite(v):
                raise ValueError('nonfinite luck attribute')
            vals.append(float(v))
        rows[name.casefold()] = (name, kind, modifier, *vals) + ((identity(entry),identity(cat),identity(value)) if identities else ())
    if len(arr) != count or len(rows) != count:
        raise ValueError('luck array changed')
    return tuple(rows[k] for k in sorted(rows))


def observe(context):
    """Return immutable values only, never live array elements or definitions."""
    pc, pawn, state, eligible = context()
    if eligible is not True:
        raise ValueError('eligible one-player local session required')
    ids = tuple(identity(o) for o in (pc, pawn, state))
    first = snapshot(pc)
    pc2, pawn2, state2, ok = context()
    if ok is not True or tuple(identity(o) for o in (pc2, pawn2, state2)) != ids:
        raise ValueError('local session changed during luck observation')
    second = snapshot(pc2)
    pc3, pawn3, state3, ok = context()
    if ok is not True or tuple(identity(o) for o in (pc3, pawn3, state3)) != ids or second != first:
        raise ValueError('luck values or local session changed during observation')
    return first


def report_lines(rows):
    lines = ['Player luck categories (read-only; not world rarity weights):']
    for name, kind, modifier, value, base in rows:
        lines.append(f'Category={name}; CategoryType={kind}; ModifierType={modifier}; Value={value!r}; BaseValue={base!r}')
    lines.append('No target selected by this report. Gear luck has isolated and opt-in continuous experimental modes; other categories remain preview only. Native drop outcomes and restoration remain unverified.')
    return lines
