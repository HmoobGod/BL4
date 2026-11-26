"""Experimental local capacity controls; only the reflected current integer is written.
Independent implementation using factual community field names and SDK declarations.
Never modify items, base attributes, SDU levels or save files.
"""
from .weapon_rates import nested, prop, live
from .gameplay_fields import identity

KEYS = frozenset(('backpack_capacity', 'bank_capacity'))
MAX_CAPACITY = 1000


def integer(owner, name):
    prop(owner._type, name, 'ZIntProperty')
    v = getattr(owner, name)
    if type(v) is not int or not 0 < v <= 9999:
        raise ValueError('invalid inventory integer: ' + name)
    return v


def inspect(pc, pawn, key):
    ps = pc.PlayerState
    if (ps is None or str(ps.Class.Name) != 'OakPlayerState' or
            live(ps) != identity(pawn.PlayerState) or identity(ps.Owner) != identity(pc)):
        raise ValueError('local inventory PlayerState ownership unavailable')
    prefix = {'backpack_capacity': 'Backpack', 'bank_capacity': 'Bank'}[key]
    container = nested(ps, prefix + 'Container', 'GbxItemContainer')
    other = nested(ps, ('Bank' if prefix == 'Backpack' else 'Backpack') + 'Container', 'GbxItemContainer')
    attr = nested(container, 'MaxSize', 'GbxAttributeInteger')
    other_attr = nested(other, 'MaxSize', 'GbxAttributeInteger')
    if identity(container) == identity(other) or identity(attr) == identity(other_attr):
        raise ValueError('aliased inventory containers')
    slots = nested(ps, prefix + 'Items', 'GbxItemSlotsContainer')
    desc = prop(slots._type, 'items', 'ZArrayProperty')
    if type(desc.Inner).__name__ != 'ZStructProperty' or str(desc.Inner.Struct.Name) != 'GbxItemContainerSlot':
        raise ValueError('inventory slot array unavailable')
    # Count every array entry, including empty/reserved ones: conservative bound,
    # not a verified count of actual occupied items. No slot writes or traversal.
    count = len(slots.items)
    if not 0 <= count <= 9999:
        raise ValueError('inventory slot count unavailable')
    value, base = integer(attr, 'Value'), integer(attr, 'BaseValue')
    return ps, container, attr, slots, value, base, count


def capture(pc, pawn, key, weak):
    ps, container, attr, slots, value, base, count = inspect(pc, pawn, key)
    if count > value:
        raise ValueError('inventory exceeds captured capacity')
    return dict(key=key, ps=weak(ps), ps_id=identity(ps), container=identity(container),
                attr=identity(attr), slots=identity(slots), base=base, baseline=value)


def resolve(pc, pawn, scope):
    ps, container, attr, slots, value, base, count = inspect(pc, pawn, scope['key'])
    old = scope['ps']()
    if (old is None or identity(old) != scope['ps_id'] or identity(ps) != scope['ps_id'] or
            (identity(container), identity(attr), identity(slots)) != (scope['container'], scope['attr'], scope['slots'])):
        raise ValueError('original inventory no longer identifiable')
    if base != scope['base']:
        raise ValueError('inventory base/SDU changed; no overwrite')
    return ((attr, 'Value', 'ZIntProperty', value),), count


def validate(scope, count, target, *, applying):
    if type(target) is not int or target < count:
        raise ValueError('capacity below inventory slot count; remove excess items first')
    if applying and (target < scope['baseline'] or target > MAX_CAPACITY):
        raise ValueError('capacity must not decrease below original or exceed experiment cap')
