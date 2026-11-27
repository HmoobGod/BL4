"""Experimental instance-scoped weapon rate paths, no SDK imports or auto hooks.
Historical GbxWeapon declarations support firerate/ReloadTime; actual game
consumption and reflection remain unverified. Identity tokens are not dereferenced.
"""
import math
import re

AMMO_KEYS = frozenset(('ammo_regen_rate', 'ammo_regen_delay'))
FIRE_KEYS = frozenset(('damage', 'fire_rate', 'weapon_spread', 'weapon_recoil'))
WEAPON_KEYS = FIRE_KEYS | frozenset(('reload',)) | AMMO_KEYS
STATES = frozenset(('Active', 'Using', 'Firing', 'Reloading'))


def token(obj):
    from .gameplay_fields import identity
    return identity(obj)


def prop(typ, name, kind):
    props = [p for p in typ._properties() if str(p.Name) == name]
    if len(props) != 1 or type(props[0]).__name__ != kind or props[0].ArrayDim != 1:
        raise ValueError('unexpected weapon descriptor: ' + name)
    return props[0]


def nested(owner, name, expected):
    typ = getattr(owner, '_type', None) or owner.Class
    p = prop(typ, name, 'ZStructProperty')
    if str(p.Struct.Name) != expected:
        raise ValueError('unexpected struct: ' + name)
    value = getattr(owner, name)
    if str(value._type.Name) != expected or token(value._type) != token(p.Struct):
        raise ValueError('struct wrapper mismatch: ' + name)
    return value


def live(obj):
    if obj is None or 'Default__' in obj._path_name():
        raise ValueError('non-instance weapon object')
    return token(obj)


def slot_entries(pawn):
    active = nested(pawn, 'ActiveWeapons', 'OakActiveWeaponsState')
    desc = prop(active._type, 'Slots', 'ZArrayProperty')
    inner = desc.Inner
    if type(inner).__name__ != 'ZStructProperty' or str(inner.Struct.Name) != 'ActiveWeaponSlot':
        raise ValueError('unexpected active slot element type')
    arr = active.Slots
    if not 0 < len(arr) <= 32:
        raise ValueError('unexpected active slot count')
    for slot in arr:
        if token(slot._type) != token(inner.Struct):
            raise ValueError('active slot wrapper mismatch')
        # One fresh traversal per slot, retaining uniqueness and exact type checks.
        names = ('Weapon', 'PendingWeapon', 'ClientPredictedPendingWeapon')
        descriptors = {name: [] for name in names}
        for d in slot._type._properties():
            name = str(d.Name)
            if name in descriptors:
                descriptors[name].append(d)
        for name, matches in descriptors.items():
            if (len(matches) != 1 or type(matches[0]).__name__ != 'ZObjectProperty'
                    or matches[0].ArrayDim != 1 or str(matches[0].PropertyClass.Name) != 'Weapon'):
                raise ValueError('unexpected slot weapon descriptor: ' + name)
    return arr


def weapons_from_entries(entries):
    """Consume entries already validated in this synchronous observation only."""
    found = {}
    for slot in entries:
        w = slot.Weapon
        if w is not None:
            found[live(w)] = w
    return found


def slots(pawn):
    return weapons_from_entries(slot_entries(pawn))


def owned_weapon(w, pawn, *, observed_slots=None):
    found = slots(pawn) if observed_slots is None else observed_slots
    if str(w.Class.Name) != 'OakWeapon' or live(w) not in found:
        raise ValueError('ordinary local weapon not identified')
    # Require actor ownership; interface/fallback guesses are not accepted.
    if token(w.Owner) != token(pawn):
        raise ValueError('weapon owner mismatch')
    if getattr(w, 'bActorIsBeingDestroyed', None) is not False:
        raise ValueError('weapon destruction state unknown')


def mode(w):
    n = w.CurrentUseModeIndex
    if type(n) is not int or not 0 <= n < 16:
        raise ValueError('unknown use mode')
    return n


def active_weapon(pawn):
    # No first-slot fallback. A second active weapon makes this experiment ineligible.
    entries = slot_entries(pawn)
    if any(slot.PendingWeapon is not None or slot.ClientPredictedPendingWeapon is not None for slot in entries):
        raise ValueError('weapon transition pending')
    found = weapons_from_entries(entries)
    candidates = [w for w in found.values() if str(w.CurrentState) in STATES]
    if len(candidates) != 1:
        raise ValueError('unique active weapon unavailable')
    w = candidates[0]
    owned_weapon(w, pawn, observed_slots=found)
    return w


def is_fire(b):
    return any(str(c.Name) == 'WeaponBehavior_Fire' for c in b.Class._superfields()) or str(b.Class.Name) == 'WeaponBehavior_Fire'


def matching_behavior(w, key, index):
    desc = prop(w.Class, 'behaviors', 'ZArrayProperty')
    if type(desc.Inner).__name__ != 'ZObjectProperty' or str(desc.Inner.PropertyClass.Name) != 'WeaponBehavior':
        raise ValueError('unexpected behavior array element type')
    arr = w.behaviors
    if not 0 < len(arr) <= 256:
        raise ValueError('unexpected weapon behavior count')
    return matching_behavior_entries(w, key, index, arr)


def matching_behavior_entries(w, key, index, arr):
    """Fresh behavior membership; metadata checked separately by full resolver."""
    if not 0 < len(arr) <= 256:
        raise ValueError('unexpected weapon behavior count')
    found = {}
    for b in arr:
        if b is None:
            continue
        # Mode identity requires an explicit name prefix, not position in the array.
        name = str(b.Name)
        m = re.fullmatch(r'UM([0-9]+)_[A-Za-z0-9_]+', name)
        if m is None or int(m.group(1)) != index:
            continue
        if (key in FIRE_KEYS and is_fire(b)) or (key == 'reload' and str(b.Class.Name) == 'WeaponBehavior_StockReload') or (key in AMMO_KEYS and str(b.Class.Name) == 'WeaponBehavior_AmmoPool'):
            if live(b) in found or token(b.Outer) != token(w):
                raise ValueError('ambiguous or foreign weapon behavior')
            found[live(b)] = b
    if len(found) != 1:
        raise ValueError('unique mode-specific behavior unavailable')
    return next(iter(found.values()))


def fields(b, key):
    from .gameplay_fields import pair
    name = {'damage': 'damage', 'fire_rate': 'firerate', 'weapon_spread': 'spread',
            'weapon_recoil': 'RecoilScale', 'reload': 'ReloadTime',
            'ammo_regen_rate': 'RegenRate', 'ammo_regen_delay': 'ConsumeRegenDelay'}[key]
    return pair(nested(b, name, 'GbxAttributeFloat'))


def capture(pawn, key, weak):
    w = active_weapon(pawn)
    if str(w.CurrentState) != 'Active':
        raise ValueError('activate with weapon idle')
    index = mode(w)
    b = matching_behavior(w, key, index)
    if key == 'damage':
        # Restrict to ordinary stock-reloading guns, not gadget/unknown fire modes.
        matching_behavior(w, 'reload', index)
    if key in AMMO_KEYS:
        # Require ordinary stock-reload behavior and existing positive native regen.
        matching_behavior(w, 'reload', index)
        from .gameplay_fields import pair
        pair(nested(b, 'RegenRate', 'GbxAttributeFloat'))
    return dict(weapon=weak(w), behavior=weak(b), weapon_id=live(w), behavior_id=live(b), mode=index, key=key)


def resolve(pawn, scope):
    w, b = scope['weapon'](), scope['behavior']()
    if live(w) != scope['weapon_id'] or live(b) != scope['behavior_id']:
        raise ValueError('original weapon or behavior lost')
    owned_weapon(w, pawn)
    current = matching_behavior(w, scope['key'], scope['mode'])
    if live(current) != live(b):
        raise ValueError('original behavior changed')
    if scope['key'] == 'damage':
        matching_behavior(w, 'reload', scope['mode'])
    # Restore only the old, still-owned instance when mode/active weapon changes.
    # If ownership or slots disappear, fail closed and never write replacement.
    try:
        eligible = live(active_weapon(pawn)) == live(w) and mode(w) == scope['mode']
    except (AttributeError, TypeError, ValueError):
        eligible = False
    return fields(current, scope['key']), eligible


def validate_targets(scope, targets):
    w = scope['weapon']()
    if w is None or str(w.CurrentState) != 'Active':
        raise ValueError('update with weapon idle')
    if scope['key'] in AMMO_KEYS:
        validate_ammo(scope)
    if scope['key'] == 'reload':
        validate_reload_floor(scope, targets)


def validate_reload_floor(scope, targets):
    # Read-only: monitor the floor even during native reloading/firing.
    from .gameplay_fields import pair
    b = scope['behavior']()
    minimum = nested(b, 'MinReloadTime', 'GbxAttributeFloat')
    floor = max(f[3] for f in pair(minimum, allow_zero=True))
    if any(t < floor for t in targets):
        raise ValueError('reload target below native minimum')


def validate_ammo(scope):
    from .gameplay_fields import pair
    w, b = scope['weapon'](), scope['behavior']()
    matching_behavior(w, 'reload', scope['mode'])
    pair(nested(b, 'RegenRate', 'GbxAttributeFloat'))


def reload_watch(pawn, scope, field_tokens):
    """Read-only steady reload observation; full descriptor audit is external.

    No cached UObject/descriptor/permission, no write target returned. All live
    membership, owner, mode, pending, field identity, scalar and floor checks
    run each callback. A changed schema identity requires the full resolver.
    """
    w, b = scope['weapon'](), scope['behavior']()
    if live(w) != scope['weapon_id'] or live(b) != scope['behavior_id']:
        raise ValueError('original weapon or behavior lost')
    active = pawn.ActiveWeapons
    entries = active.Slots
    if not 0 < len(entries) <= 32:
        raise ValueError('unexpected active slot count')
    slot_types = tuple(token(slot._type) for slot in entries)
    if any(slot.PendingWeapon is not None or slot.ClientPredictedPendingWeapon is not None for slot in entries):
        raise ValueError('weapon transition pending')
    found = weapons_from_entries(entries)
    owned_weapon(w, pawn, observed_slots=found)
    candidates = [wid for wid, obj in found.items() if str(obj.CurrentState) in STATES]
    if candidates != [scope['weapon_id']] or mode(w) != scope['mode']:
        raise ValueError('active weapon or mode changed')
    current = matching_behavior_entries(w, 'reload', scope['mode'], w.behaviors)
    if live(current) != scope['behavior_id']:
        raise ValueError('original behavior changed')
    reload, minimum = current.ReloadTime, current.MinReloadTime
    schema = (token(active._type), slot_types, token(w.Class), token(current.Class),
              token(reload._type), token(minimum._type), token(minimum))
    if tuple((token(reload), name) for name in ('Value', 'BaseValue')) != tuple((i,n) for i,n,_ in field_tokens):
        raise ValueError('reflected field identity changed')
    values = (reload.Value, reload.BaseValue)
    floor = (minimum.Value, minimum.BaseValue)
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 < v <= 1e6 for v in values):
        raise ValueError('invalid reload value')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1e6 for v in floor):
        raise ValueError('invalid reload minimum')
    if min(values) < max(floor):
        raise ValueError('reload target below native minimum')
    return schema, tuple(float(v) for v in values)
