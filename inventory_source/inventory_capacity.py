"""Source-only capacity readback experiment; no hook, SDK import, or loader entrypoint.

Independent implementation of the reflected Value-only mechanism described by
flameaway/bl4-fix, mods/bl4_backpack_size/limits.py, tree 7dbe8410c72fcd6f0eb5cff6675381e962d66cec (GPL-3.0).
No upstream implementation copied. Native caller integration and execution HOLD.
"""
from dataclasses import dataclass

CONFIRM = 'DISPOSABLE OFFLINE CAPACITY READBACK ONLY'
FIELDS = {'backpack': ('BackpackContainer', 'BackpackItems'),
          'bank': ('BankContainer', 'BankItems')}


class CapacityFault(RuntimeError):
    pass


def struct_name(obj):
    return str(getattr(getattr(obj, '_type', None), 'Name', ''))


@dataclass(frozen=True)
class Sample:
    value: int
    base: int
    slots: int
    profile: int


def sample(player_state, kind):
    """Resolve embedded structs afresh; never cache a native struct wrapper."""
    container_name, items_name = FIELDS[kind]
    if str(player_state.Class.Name) != 'OakPlayerState':
        raise CapacityFault('wrong player state class')
    container = getattr(player_state, container_name)
    items = getattr(player_state, items_name)
    if (struct_name(container) != 'GbxItemContainer'
            or struct_name(items) != 'GbxItemSlotsContainer'):
        raise CapacityFault('container type mismatch')
    field = container.MaxSize
    if struct_name(field) != 'GbxAttributeInteger':
        raise CapacityFault('attribute type mismatch')
    s = Sample(field.Value, field.BaseValue, len(items.items), container.ProfileId)
    if any(type(x) is not int for x in (s.value, s.base, s.slots, s.profile)):
        raise CapacityFault('integer fields required')
    if not (1 <= s.base <= s.value <= 10000 and 0 <= s.profile <= 255):
        raise CapacityFault('invalid capacity or profile')
    if not 1 <= s.slots <= s.value:
        raise CapacityFault('empty, unloaded, or over-capacity slot array')
    return s, field


def readback(kind, confirmation, original_context):
    """One synchronous +1/restore probe, NOT a sustained gameplay feature.

    original_context must revalidate exact R10 strict standalone, local authority,
    sole PlayerState, camera/thread, idle, original world and weak identities on
    EVERY call. It must return the same live local OakPlayerState or raise.
    This module is deliberately not wired to any hook or console command yet.
    Caller must provide process one-shot latch and separate native authorization.
    """
    if confirmation != CONFIRM or kind not in FIELDS:
        raise CapacityFault('invalid opt-in or container')
    initial, _ = sample(original_context(), kind)
    if initial.value >= 10000:
        raise CapacityFault('trial ceiling')
    target = initial.value + 1

    def current():
        s, f = sample(original_context(), kind)
        if (s.base, s.slots, s.profile) != (initial.base, initial.slots, initial.profile):
            raise CapacityFault('SDU, slot count, or profile changed')
        return s, f

    before, field = current()
    if before != initial:
        raise CapacityFault('baseline changed before write')
    try:
        field.Value = target
        active, _ = current()
        if active.value != target:
            raise CapacityFault('activation readback mismatch')
    finally:
        # Even a setter that throws after writing gets a guarded restore attempt.
        # A different value or lost identity is a hard fault, never overwritten.
        restored, field = current()
        if restored.value == target:
            field.Value = initial.value
            restored, _ = current()
        if restored != initial:
            raise CapacityFault('restoration unverified; exit disposable session')
    return initial.value, target, restored.value
