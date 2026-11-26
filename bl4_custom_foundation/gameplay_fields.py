"""Narrow community-derived reflected-field adapters; no automatic writes.
Loot Treadmill (Noah Lincke, MIT) and Squ1ggs Player Movement, Damage & More,
Resources & Cooldowns (MIT). Pinned source details in SOURCES.md.
"""
import math
import struct

# Distinct owners and meanings; no aliases between features.
FEATURES = {
    'backpack_capacity': ('Backpack capacity (slots; 1 restores)', 1., 1000.),
    'bank_capacity': ('Bank capacity (slots; 1 restores)', 1., 1000.),
    'legendary_weight': ('Legendary rarity weight', .1, 10.),
    'common_weight': ('Common rarity weight', 0., 10.),
    'uncommon_weight': ('Uncommon rarity weight', 0., 10.),
    'jump': ('Jump velocity multiplier', .5, 5.),
    'dash_speed': ('Dash speed multiplier (experimental)', .5, 3.),
    'glide_speed': ('Glide speed multiplier (experimental)', .5, 3.),
    'double_jump_cost': ('Double-jump energy cost multiplier (experimental)', .1, 3.),
    'dash_cost': ('Dash energy cost multiplier (experimental)', .1, 3.),
    'glide_cost': ('Glide energy cost multiplier (experimental)', .1, 3.),
    'glide_air_control': ('Glide air control multiplier (experimental)', .5, 3.),
    'glide_boost': ('Glide speed boost multiplier (experimental)', .5, 3.),
    'glide_acceleration': ('Glide acceleration multiplier (experimental)', .5, 3.),
    'glide_deceleration': ('Glide deceleration multiplier (experimental)', .5, 3.),
    'grapple_cost': ('Grapple energy cost multiplier (experimental)', .1, 3.),
    'slam_cost': ('Ground-slam energy cost multiplier (experimental)', .1, 3.),
    'ladder_ascend': ('Ladder ascent speed multiplier (experimental)', .5, 3.),
    'ladder_descend': ('Ladder descent speed multiplier (experimental)', .5, 3.),
    'slam_height': ('Ground-slam height scalar (experimental)', .5, 2.),
    'player_ammo_regen': ('Existing player ammo regeneration rate (experimental)', .5, 3.),
    'slide_speed': ('Active slide speed scale (experimental)', .5, 2.),
    'ground_friction': ('Ground friction multiplier (experimental)', .5, 2.),
    'braking_friction': ('Braking friction factor multiplier (experimental)', .5, 2.),
    'gravity': ('Local gravity multiplier', .5, 1.5),
    'fire_damage': ('Fire damage multiplier', .5, 5.),
    'repair_cooldown': ('Repair-kit cooldown duration multiplier', .1, 5.),
    'damage': ('Damage multiplier', .5, 5.),
    'weapon_spread': ('Weapon spread scale (experimental)', .1, 3.),
    'weapon_recoil': ('Weapon recoil scale (experimental)', .1, 3.),
    'fire_rate': ('Weapon fire rate multiplier (experimental)', .5, 3.),
    'reload': ('Weapon reload speed multiplier (experimental)', .5, 3.),
    'swap_time': ('Weapon swap time scale (experimental)', .5, 3.),
    'ammo_regen_rate': ('Existing ammo regeneration rate (experimental)', .5, 3.),
    'ammo_regen_delay': ('Existing ammo regeneration delay speed (experimental)', .5, 3.),
    'shield_regen_rate': ('Equipped energy shield recharge rate (experimental)', .5, 3.),
    'shield_regen_delay': ('Equipped energy shield recharge delay speed (experimental)', .5, 3.),
    'grenade_cooldown': ('Grenade gadget cooldown speed (experimental)', .5, 3.),
    'lifesteal_rate': ('Existing life-steal rate (experimental)', .5, 3.),
    'lifesteal_fraction': ('Existing life-steal percentage multiplier (experimental)', .5, 3.),
    'repair_health': ('Repair-kit healing amount multiplier', .5, 5.),
    'damage_taken': ('Damage taken multiplier', .1, 5.),
    'shock_damage': ('Shock damage multiplier', .5, 5.),
    'corrosive_damage': ('Corrosive damage multiplier', .5, 5.),
    'cryo_damage': ('Cryo damage multiplier', .5, 5.),
    'radiation_damage': ('Radiation damage multiplier', .5, 5.),
    'sprint': ('Sprint-only speed floor (reference multiplier)', 1., 3.),
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

def gravity(pawn, state):
    # Apex uses the local CharacterMovement component, not a shared jump definition.
    fields = owned_movement_scalar(pawn, 'GravityScale')
    if identity(fields[0][0]) != identity(pawn.CharacterMovement):
        raise ValueError('Apex CharacterMovement identity mismatch')
    return fields


def local_friction(pawn, field):
    # Existing native on-foot friction fields, not a slide-only adjustment.
    fields = owned_movement_scalar(pawn, field)
    comp = pawn.CharacterMovement
    if (identity(fields[0][0]) != identity(comp)
            or str(comp.Class.Name) != 'OakCharacterMovementComponent'
            or identity(comp.OakCharacterOwner) != identity(pawn)):
        raise ValueError('local Oak movement component unavailable')
    return fields


def local_move_pair(pawn, field):
    """Exact local Oak movement component; no jump-goal or shared definition writes."""
    from .weapon_rates import nested
    comp = pawn.CharacterMovement
    if (comp is None or str(comp.Class.Name) != 'OakCharacterMovementComponent'
            or 'Default__' in comp._path_name() or identity(comp.OakCharacterOwner) != identity(pawn)):
        raise ValueError('local Oak movement component unavailable')
    for name in ('CharacterOwner', 'PawnOwner'):
        owner = getattr(comp, name, None)
        if owner is not None and identity(owner) != identity(pawn):
            raise ValueError('movement owner mismatch')
    return pair(nested(comp, field, 'GbxAttributeFloat'))


# Apex Movement's community-tested local scale consumer. The shared Move_Slide
# definition is read only; the only writable field is the instance Value.
SLIDE_PATH = '/Game/PlayerCharacters/_Shared/Tricks/ControlledMoves/Move_Slide.Move_Slide'


def slide_component(pawn):
    comp = pawn.CharacterMovement
    if (comp is None or str(comp.Class.Name) != 'OakCharacterMovementComponent'
            or 'Default__' in comp._path_name() or identity(comp.OakCharacterOwner) != identity(pawn)):
        raise ValueError('local Oak movement component unavailable')
    for name in ('CharacterOwner', 'PawnOwner'):
        owner = getattr(comp, name, None)
        if owner is not None and identity(owner) != identity(pawn):
            raise ValueError('movement owner mismatch')
    return comp


def slide_scale(pawn):
    from .weapon_rates import nested
    attribute = nested(slide_component(pawn), 'MaxGroundSpeedScale', 'GbxAttributeFloat')
    return scalar(attribute, 'Value'), scalar(attribute, 'BaseValue')


def slide_active(pawn):
    """Positive exact move + native predicate; no crouch/airborne fallback."""
    from .weapon_rates import nested, prop
    try:
        comp = slide_component(pawn)
        data = nested(comp, 'ControlledMoveReplicationData', 'ControlledMoveReplicationData')
        descriptor = prop(data._type, 'ControlledMove', 'ZObjectProperty')
        if str(descriptor.PropertyClass.Name) != 'ControlledMove':
            return False
        move = data.ControlledMove
        if (move is None or move._path_name() != SLIDE_PATH or str(move.Class.Name) != 'OakControlledMove'
                or move.bSpeedAffectedByMaxGroundSpeedScale is not True):
            return False
        f = comp.IsPerformingSpecificControlledMove
        fn = f.func
        if fn._path_name() != '/Script/GbxGame.GbxCharacterMovementComponent:IsPerformingSpecificControlledMove' or fn.NumParams != 2:
            return False
        props = tuple(fn._properties())
        if (len(props) != 2 or any(p.ArrayDim != 1 for p in props)
                or tuple((str(p.Name), type(p).__name__) for p in props) != (('ControlledMove','ZObjectProperty'),('ReturnValue','ZBoolProperty'))
                or props[0].PropertyClass._path_name() != '/Script/GbxGame.ControlledMove'):
            return False
        if f(move) is not True:
            return False
        # Fresh replication identity after the read-only native predicate.
        current_comp = slide_component(pawn)
        if identity(current_comp) != identity(comp):
            return False
        current = nested(current_comp, 'ControlledMoveReplicationData', 'ControlledMoveReplicationData').ControlledMove
        return (current is not None and identity(current) == identity(move) and current._path_name() == SLIDE_PATH
                and current.bSpeedAffectedByMaxGroundSpeedScale is True)
    except Exception:
        return False


def player_ammo_regen(pawn, state):
    from .weapon_rates import nested
    if str(pawn.Class.Name) != 'OakCharacter' or 'Default__' in pawn._path_name():
        raise ValueError('live local OakCharacter required')
    return pair(nested(pawn, 'ammoregenrate', 'GbxAttributeFloat'))


def combat(pawn, state):
    # Verified source: ElementalDamageModifiers.FireModifier is a pawn pair.
    return pair(pawn.ElementalDamageModifiers.FireModifier)


def recovery(pawn, state):
    # Verified source: HealthState.RepairKitCooldown is a pawn pair, in seconds.
    return pair(pawn.HealthState.RepairKitCooldown)


def repair_health(pawn, state):
    from .weapon_rates import nested
    health = nested(pawn, 'HealthState', 'OakCharacterHealthState')
    if identity(health.owner) != identity(pawn):
        raise ValueError('repair kit owner mismatch')
    return pair(nested(health, 'RepairKitHealth', 'GbxAttributeFloat'))


def swap_time(pawn, state):
    # Pawn-owned native time scale, not a shared weapon definition.
    from .weapon_rates import nested
    if pawn is None or 'Default__' in pawn._path_name():
        raise ValueError('live player pawn required')
    return pair(nested(pawn, 'WeaponSwapTimeScale', 'GbxAttributeFloat'))


def lifesteal_rate(pawn, state):
    # Only the existing local rate; do not turn on life-steal, change its cap,
    # or touch any health pool value. Historical OakDamageState declaration.
    from .weapon_rates import nested
    damage = nested(pawn, 'DamageState', 'OakDamageState')
    if identity(damage.owner) != identity(pawn):
        raise ValueError('life-steal owner mismatch')
    return pair(nested(damage, 'lifestealrate', 'GbxAttributeFloat'))


def lifesteal_fraction(pawn, state):
    # Resolve the writable pair separately from admission: loss of the native
    # rate/cap must not prevent restoration of an otherwise intact original pair.
    from .weapon_rates import nested
    damage = nested(pawn, 'DamageState', 'OakDamageState')
    if identity(damage.owner) != identity(pawn):
        raise ValueError('life-steal owner mismatch')
    return pair(nested(damage, 'lifestealpercent', 'GbxAttributeFloat'))


def validate_lifesteal_fraction(pawn, baseline, targets):
    from .weapon_rates import nested
    damage = nested(pawn, 'DamageState', 'OakDamageState')
    if identity(damage.owner) != identity(pawn):
        raise ValueError('life-steal owner mismatch')
    # Conservative normalized-fraction experiment only. Never seed a zero
    # baseline, modify the cap, or assume values above one are percentages.
    if any(not 0 < v <= 1 for v in (*baseline, *targets)):
        raise ValueError('life-steal fraction outside normalized bounds')
    rate = pair(nested(damage, 'lifestealrate', 'GbxAttributeFloat'))
    cap = pair(nested(damage, 'lifestealratecap', 'GbxAttributeFloat'))
    if rate[0][3] != rate[1][3] or cap[0][3] != cap[1][3] or rate[0][3] > cap[0][3]:
        raise ValueError('existing life-steal rate/cap uncertain')
    return describe_fields(rate + cap)[1:]


def validate_lifesteal(pawn, targets):
    from .weapon_rates import nested
    damage = nested(pawn, 'DamageState', 'OakDamageState')
    if identity(damage.owner) != identity(pawn):
        raise ValueError('life-steal owner mismatch')
    # Positive existing percent and cap only; conservative candidate bound.
    pair(nested(damage, 'lifestealpercent', 'GbxAttributeFloat'))
    cap = min(f[3] for f in pair(nested(damage, 'lifestealratecap', 'GbxAttributeFloat')))
    if any(t > cap for t in targets):
        raise ValueError('life-steal target above existing cap')


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
           'repair_health': repair_health,
           'swap_time': swap_time,
           'lifesteal_rate': lifesteal_rate,
           'lifesteal_fraction': lifesteal_fraction,
           'damage': lambda p, s: pair(p.DamageCauserData.DamageDealtMultiplier),
           'damage_taken': lambda p, s: pair(p.DamageState.DamageTakenMultiplier),
           'shock_damage': lambda p, s: pair(p.ElementalDamageModifiers.ShockModifier),
           'corrosive_damage': lambda p, s: pair(p.ElementalDamageModifiers.CorrosiveModifier),
           'cryo_damage': lambda p, s: pair(p.ElementalDamageModifiers.CryoModifier),
           'radiation_damage': lambda p, s: pair(p.ElementalDamageModifiers.RadiationModifier),
           'walk_speed': walk_speed,
           'sprint': walk_speed,
           'gravity': gravity,
           'slide_speed': lambda p, s: (slide_scale(p)[0],),
           'ground_friction': lambda p, s: local_friction(p, 'GroundFriction'),
           'braking_friction': lambda p, s: local_friction(p, 'BrakingFrictionFactor'),
           'dash_speed': lambda p, s: local_move_pair(p, 'DashSpeed'),
           'glide_speed': lambda p, s: local_move_pair(p, 'GlidingSpeed'),
           'double_jump_cost': lambda p, s: local_move_pair(p, 'VaultPowerCost_DoubleJump'),
           'dash_cost': lambda p, s: local_move_pair(p, 'VaultPowerCost_Dash'),
           'glide_cost': lambda p, s: local_move_pair(p, 'VaultPowerCost_Glide'),
           'glide_air_control': lambda p, s: local_move_pair(p, 'GlidingAirControl'),
           'glide_boost': lambda p, s: local_move_pair(p, 'GlidingSpeedBoost'),
           'glide_acceleration': lambda p, s: local_move_pair(p, 'GlidingAcceleration'),
           'glide_deceleration': lambda p, s: local_move_pair(p, 'GlidingDeceleration'),
           'grapple_cost': lambda p, s: local_move_pair(p, 'VaultPowerCost_Grapple'),
           'slam_cost': lambda p, s: local_move_pair(p, 'VaultPowerCost_GroundSlam'),
           'ladder_ascend': lambda p, s: local_move_pair(p, 'MaxLadderAscendSpeed'),
           'ladder_descend': lambda p, s: local_move_pair(p, 'MaxLadderDescendSpeed'),
           'slam_height': lambda p, s: local_move_pair(p, 'GroundSlamHeightScalar'),
           'player_ammo_regen': player_ammo_regen,
           'healing_received': lambda p, s: pair(p.DamageState.HealingReceivedMultiplier),
           'rare_weight': lambda p, s: (scalar(s.RarityState.RareModifier, 'Value'),),
           'epic_weight': epic,
           'pearlescent_weight': pearlescent,
           'repair_duration': lambda p, s: pair(p.HealthState.RepairKitDuration)}


def describe_fields(fields):
    tokens = tuple((identity(o), n, k) for o, n, k, _ in fields)
    if len(set(tokens)) != len(tokens):
        raise ValueError('duplicate field ownership')
    return fields, tokens, tuple(v for _, _, _, v in fields)


def read_fields(key, pawn, state):
    if key not in RESOLVE:
        raise ValueError('feature HOLD')
    return describe_fields(RESOLVE[key](pawn, state))


def target_values(key, baseline, tokens, selection):
    _, low, high = FEATURES[key]
    if type(selection) not in (int, float) or not math.isfinite(selection) or not low <= selection <= high:
        raise ValueError('invalid multiplier')
    if key in ('backpack_capacity', 'bank_capacity'):
        if selection != int(selection):
            raise ValueError('capacity requires whole slots')
        return tuple(int(selection) for _ in baseline)
    # Exact representable native targets, not fuzzy comparisons with foreign writes.
    if key in RARITY_KEYS and selection != round(selection, 1):
        raise ValueError('rarity weight uses 0.1 increments')
    result = []
    for base, (_, _, kind) in zip(baseline, tokens, strict=True):
        v = base / selection if key in ('reload', 'ammo_regen_delay', 'shield_regen_delay', 'grenade_cooldown') else base * selection
        if kind == 'ZFloatProperty':
            v = struct.unpack('<f', struct.pack('<f', v))[0]
        if not math.isfinite(v) or not (0 <= v <= 1e6 if key in ZERO_RARITY_KEYS and selection == 0 else 0 < v <= 1e6):
            raise ValueError('target outside verified scalar bounds')
        result.append(v)
    return tuple(result)
