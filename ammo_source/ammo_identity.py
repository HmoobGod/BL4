"""Read-only ammo candidate classification for the future auto-ammo feature.

Independent implementation informed by jlangowells/bl4_loot_filter, GPL-3.0,
commit 41da0910f3c1f6ebac42ea3362bc92e65e59ebc0 (__init__.py body/material
classification). No upstream code copied. The classifier is not proof of
local ownership, ordinary pickup eligibility or safe collection. No SDK import,
world enumeration, hook registration, teleport, overlap replay or collection.
"""
from dataclasses import dataclass
import re

# Narrow documented ordinary firearm categories; ordnance and other resources
# intentionally excluded. Unknown spellings fail closed.
WEAPON_FAMILY = {
    'sniper': 'sniper', 'shotguns': 'shotgun', 'shotgun': 'shotgun',
    'assaultrifles': 'assault_rifle', 'assault': 'assault_rifle',
    'smg': 'smg', 'pistols': 'pistol', 'pistol': 'pistol',
}
_SEGMENT = re.compile(r'[A-Za-z0-9_]+\Z')
_MATERIAL = re.compile(r'MI_AMMO_([A-Za-z]+)(?:_[A-Za-z0-9]+)*\Z', re.ASCII | re.IGNORECASE)


@dataclass(frozen=True)
class AmmoCandidate:
    actor_identity: int
    body_package: str
    material: str
    family: str


def body_is_ammo(package):
    """Only original-game ammo packages; no material-only or DLC fallback."""
    if type(package) is not str or len(package) > 512:
        return False
    parts = package.split('/')
    return (len(parts) >= 5 and parts[:3] == ['', 'Game', 'Pickups']
            and parts[3] in ('Ammo', 'ammo')
            and all(_SEGMENT.fullmatch(p) is not None for p in parts[4:]))


def material_family(name):
    if type(name) is not str or len(name) > 128:
        return None
    match = _MATERIAL.fullmatch(name)
    return None if match is None else WEAPON_FAMILY.get(match.group(1).lower())


def identify(actor_class, body_package, material, actor_identity):
    """Requires agreement of two cues. A result is a candidate, never admission."""
    if (actor_class != 'InventoryPickup' or type(actor_class) is not str
            or type(actor_identity) is not int or actor_identity <= 0
            or not body_is_ammo(body_package)):
        return None
    family = material_family(material)
    if family is None:
        return None
    return AmmoCandidate(actor_identity, body_package, material, family)


def _identity(obj):
    if obj is None:
        raise ValueError('object missing')
    n = obj._get_address()
    if type(n) is not int or n <= 0:
        raise ValueError('invalid object identity')
    return n


def inspect_candidate(actor, *, still_current, excluded_identities):
    """Bounded read-only SDK adapter; caller must independently establish scope.

    still_current must revalidate live weak identity, original world, local
    player, and authorized callback thread. excluded_identities must come from
    a complete, current-world vending-display exclusion check. No implementation
    of that caller exists here; never infer ownership from this classifier.
    """
    try:
        if still_current() is not True or type(excluded_identities) is not frozenset:
            return None
        token = _identity(actor)
        if token in excluded_identities or str(actor.Class.Name) != 'InventoryPickup':
            return None
        if actor.bActorIsBeingDestroyed is not False:
            return None
        body = actor.BodyData
        outer = body.Outer
        root = actor.RootPrimitiveComponent
        before = (_identity(body), _identity(outer), _identity(root))
        package = str(outer.Name)
        if not body_is_ammo(package):
            return None
        if still_current() is not True:
            return None
        count = root.GetNumMaterials()
        if type(count) is not int or not 1 <= count <= 32:
            return None
        material = root.GetMaterial(0)
        material_id = _identity(material)
        name = str(material.Name)
        result = identify('InventoryPickup', package, name, token)
        if result is None or still_current() is not True:
            return None
        if (actor.bActorIsBeingDestroyed is not False or _identity(actor) != token
                or str(actor.Class.Name) != 'InventoryPickup'):
            return None
        now_body = actor.BodyData
        now_outer = now_body.Outer
        now_root = actor.RootPrimitiveComponent
        if (before != (_identity(now_body), _identity(now_outer), _identity(now_root))
                or str(now_outer.Name) != package or now_root.GetNumMaterials() != count):
            return None
        now_material = now_root.GetMaterial(0)
        if _identity(now_material) != material_id or str(now_material.Name) != name:
            return None
        return result if still_current() is True else None
    except Exception:
        return None
