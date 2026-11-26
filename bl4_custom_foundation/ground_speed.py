"""Modified narrow ground-speed adapter, based on Apex Movement by Kevin-hDev.
Copyright 2026 Kevin-hDev. Apache-2.0; see LICENSE-Apex.txt and SOURCES.md.
Only the raising floor behavior is adapted; no slow walk, guest, asset or startup writes.
"""
import math
import struct
from .gameplay_fields import identity

# Author measured reference speeds (2026-09-15), not this owner's measured baseline.
WALK_REFERENCE = 540.0
SPRINT_REFERENCE = 828.0

def is_player_animation(pc, pawn, obj):
    character = pc.OakCharacter
    if character is None or identity(character) != identity(pawn):
        return False
    animation = character.Mesh.GetAnimInstance()
    return animation is not None and identity(animation) == identity(obj)

def sprinting(pawn):
    value = pawn.CharacterMovement.bIsSprinting
    if type(value) is not bool:
        raise ValueError('sprint state unavailable')
    return value

def floor_target(baseline, tokens, selection, sprint, *, sprint_only=False):
    if type(selection) not in (int, float) or not math.isfinite(selection) or not 1 < selection <= 3:
        raise ValueError('ground speed requires >1x through 3x; 1x restores')
    if type(sprint) is not bool or len(tokens) != 1 or len(baseline) != 1 or tokens[0][1] != 'MinAnalogWalkSpeed':
        raise ValueError('invalid ground floor context')
    if type(sprint_only) is not bool:
        raise ValueError('invalid ground mode')
    value = baseline[0] if sprint_only and not sprint else max(baseline[0], (SPRINT_REFERENCE if sprint else WALK_REFERENCE) * selection)
    if tokens[0][2] == 'ZFloatProperty':
        value = struct.unpack('<f', struct.pack('<f', value))[0]
    if not math.isfinite(value) or not 0 <= value <= 1e6:
        raise ValueError('ground floor out of bounds')
    return (value,)
