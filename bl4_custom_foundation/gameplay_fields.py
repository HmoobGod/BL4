"""Narrow community-derived reflected-field adapters; no automatic writes.
Loot Treadmill (Noah Lincke, MIT) and Squ1ggs Player Movement, Damage & More,
Resources & Cooldowns (MIT). Pinned source details in SOURCES.md.
"""
import math
import struct

# Distinct owners and meanings; no aliases between features.
FEATURES = {
    'legendary_weight': ('Legendary rarity weight', .1, 10.),
    'common_weight': ('Common rarity weight', 0., 10.),
    'uncommon_weight': ('Uncommon rarity weight', 0., 10.),
    'jump': ('Jump velocity multiplier', .5, 5.),
    'fire_damage': ('Fire damage multiplier', .5, 5.),
    'repair_cooldown': ('Repair-kit cooldown duration multiplier', .1, 5.),
    'damage': ('Damage multiplier', .5, 5.),
    'damage_taken': ('Damage taken multiplier', .1, 5.),
    'shock_damage': ('Shock damage multiplier', .5, 5.),
    'corrosive_damage': ('Corrosive damage multiplier', .5, 5.),
    'cryo_damage': ('Cryo damage multiplier', .5, 5.),
    'radiation_damage': ('Radiation damage multiplier', .5, 5.),
    'walk_speed': ('Ground speed floor (reference multiplier)', 1., 3.),
    'healing_received': ('Healing received multiplier', .5, 5.),
    'rare_weight': ('Rare rarity weight', .1, 10.),
    'epic_weight': ('Epic rarity weight', .1, 10.),
    'pearlescent_weight': ('Pearlescent rarity weight', .1, 10.),
    'repair_duration': ('Repair-kit healing duration multiplier', .5, 5.),
}


ZERO_RARITY_KEYS = frozenset(('common_weight', 'uncommon_weight'))
RARITY_KEYS = ZERO_RARITY_KEYS | frozenset(('legendary_weight', 'rare_weight', 'epic_weight', 'pearlescent_weight'))

def identity(obj):
    token = obj._get_address()
    if type(token) is not int or token <= 0:
        raise ValueError('SDK identity unavailable')
    return token


def scalar(owner, name, *, allow_zero=False):
    typ = getattr(owner, '_type', None)
    if typ is None:
        typ = owner.Class
    props = [p for p in typ._properties() if str(p.Name) == name]
    if len(props) != 1 or props[0].ArrayDim != 1:
        raise ValueError('unsupported or ambiguous scalar: ' + name)
    kind = type(props[0]).__name__
    if kind not in ('ZFloatProperty', 'ZDoubleProperty'):
        raise ValueError('unsupported scalar type: ' + name)
    v = getattr(owner, name)
    if type(v) not in (int, float) or not math.isfinite(v) or not (0 <= v <= 1e6 if name == 'MinAnalogWalkSpeed' or allow_zero else 0 < v <= 1e6):
        raise ValueError('invalid/nonpositive baseline or value: ' + name)
    return owner, name, kind, float(v)


def pair(owner):
    # Do not guess extra fields or use the upstream blind fallback setter.
    return (scalar(owner, 'Value'), scalar(owner, 'BaseValue'))


def loot(pawn, state):
    return (scalar(state.RarityState.LegendaryModifier, 'Value'),)


def owned_movement_scalar(pawn, name_of_field):
    # Source's ordered pawn component names, with strict ownership and no global scan.
    candidates = {}
    pawn_id = identity(pawn)
    for name in ('CharMoveComp', 'CharacterMovement', 'OakCharacterMovement',
                 'GbxCharacterMovement', 'MovementComponent'):
        comp = getattr(pawn, name, None)
        if comp is None:
            continue
        try:
            token = identity(comp)
            # Already verified this exact component during this resolution.
            # No ownership or reflection result is retained across callbacks.
            if token in candidates:
                continue
            if 'Default__' in comp._path_name():
                continue
            owners = [getattr(comp, x, None) for x in ('OakCharacterOwner', 'CharacterOwner', 'PawnOwner')]
            if not any(o is not None for o in owners):
                continue
            if any(o is not None and identity(o) != pawn_id for o in owners):
                continue
            # Distinct candidates still checked. Aliases of the same owned component
            # need only one reflection scan within this call, never cached across frames.
            candidates[token] = scalar(comp, name_of_field)
        except (AttributeError, TypeError, ValueError):
            continue
    if len(candidates) != 1:
        raise ValueError('unique owned scalar ' + name_of_field + ' unavailable')
    return (next(iter(candidates.values())),)


def movement(pawn, state):
    return owned_movement_scalar(pawn, 'JumpZVelocity')

def walk_speed(pawn, state):
    # Apex ground_speed.py uses CharacterMovement specifically, not an arbitrary alias.
    fields = owned_movement_scalar(pawn, 'MinAnalogWalkSpeed')
    if identity(fields[0][0]) != identity(pawn.CharacterMovement):
        raise ValueError('Apex CharacterMovement identity mismatch')
    return fields

def combat(pawn, state):
    # Verified source: ElementalDamageModifiers.FireModifier is a pawn pair.
    return pair(pawn.ElementalDamageModifiers.FireModifier)


def recovery(pawn, state):
    # Verified source: HealthState.RepairKitCooldown is a pawn pair, in seconds.
    return pair(pawn.HealthState.RepairKitCooldown)


def epic(pawn, state):
    # Upstream lists VeryRareModifier and EpicModifier; ambiguous distinct
    # candidates are not safe to guess between. Only exact reflected fields.
    rarity = state.RarityState
    candidates = {}
    for name in ('VeryRareModifier', 'EpicModifier'):
        modifier = getattr(rarity, name, None)
        if modifier is not None:
            field = scalar(modifier, 'Value')
            candidates[identity(modifier)] = field
    if len(candidates) != 1:
        raise ValueError('unique epic rarity field unavailable')
    return (next(iter(candidates.values())),)


def pearlescent(pawn, state):
    # Community source lists both names; reject distinct objects, never guess.
    candidates = {}
    for name in ('PearlescentModifier', 'PearlModifier'):
        modifier = getattr(state.RarityState, name, None)
        if modifier is not None:
            token = identity(modifier)
            if token not in candidates:
                candidates[token] = scalar(modifier, 'Value')
    if len(candidates) != 1:
        raise ValueError('unique pearlescent rarity field unavailable')
    return (next(iter(candidates.values())),)


RESOLVE = {'legendary_weight': loot, 'jump': movement, 'fire_damage': combat,
           'common_weight': lambda p, s: (scalar(s.RarityState.CommonModifier, 'Value', allow_zero=True),),
           'uncommon_weight': lambda p, s: (scalar(s.RarityState.UncommonModifier, 'Value', allow_zero=True),),
           'repair_cooldown': recovery,
           'damage': lambda p, s: pair(p.DamageCauserData.DamageDealtMultiplier),
           'damage_taken': lambda p, s: pair(p.DamageState.DamageTakenMultiplier),
           'shock_damage': lambda p, s: pair(p.ElementalDamageModifiers.ShockModifier),
           'corrosive_damage': lambda p, s: pair(p.ElementalDamageModifiers.CorrosiveModifier),
           'cryo_damage': lambda p, s: pair(p.ElementalDamageModifiers.CryoModifier),
           'radiation_damage': lambda p, s: pair(p.ElementalDamageModifiers.RadiationModifier),
           'walk_speed': walk_speed,
           'healing_received': lambda p, s: pair(p.DamageState.HealingReceivedMultiplier),
           'rare_weight': lambda p, s: (scalar(s.RarityState.RareModifier, 'Value'),),
           'epic_weight': epic,
           'pearlescent_weight': pearlescent,
           'repair_duration': lambda p, s: pair(p.HealthState.RepairKitDuration)}


def read_fields(key, pawn, state):
    if key not in RESOLVE:
        raise ValueError('feature HOLD')
    fields = RESOLVE[key](pawn, state)
    tokens = tuple((identity(o), n, k) for o, n, k, _ in fields)
    if len(set(tokens)) != len(tokens):
        raise ValueError('duplicate field ownership')
    return fields, tokens, tuple(v for _, _, _, v in fields)


def target_values(key, baseline, tokens, selection):
    _, low, high = FEATURES[key]
    if type(selection) not in (int, float) or not math.isfinite(selection) or not low <= selection <= high:
        raise ValueError('invalid multiplier')
    # Exact representable native targets, not fuzzy comparisons with foreign writes.
    if key in RARITY_KEYS and selection != round(selection, 1):
        raise ValueError('rarity weight uses 0.1 increments')
    result = []
    for base, (_, _, kind) in zip(baseline, tokens, strict=True):
        v = base * selection
        if kind == 'ZFloatProperty':
            v = struct.unpack('<f', struct.pack('<f', v))[0]
        if not math.isfinite(v) or not (0 <= v <= 1e6 if key in ZERO_RARITY_KEYS and selection == 0 else 0 < v <= 1e6):
            raise ValueError('target outside verified scalar bounds')
        result.append(v)
    return tuple(result)
