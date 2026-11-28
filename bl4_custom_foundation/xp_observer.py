"""Read-only native XP progression, globals consumer, and kill-award telemetry observer.

Strictly read-only diagnostic module: NEVER grants XP, NEVER calls
BP_SetExperienceLevel, NEVER mutates shared difficulty tables, NEVER writes
ExperienceState, and NEVER replays AwardKillExperienceToParty.

Grounded in pinned historical SDK declarations
(F100rwater/borderlands4_SDK_Dumper7 a958797d4dc51ff56ec0891db0039591abb58a9a):
- OakPlayerState.ExperienceState (TArray<FPlayerExperienceState>, OakGame_classes.hpp:14212)
- FPlayerExperienceState.ExperienceId (typed FSName struct, OakGame_structs.hpp:22384-22396)
- FOakGlobalsExperience.CombatExperienceModifier (FGbxDefPtr, OakGame_structs.hpp:20720-20734)
- OakExperienceStatics.AwardKillExperienceToParty(ContextActor, OptionalKiller)
"""
from collections import deque
import math
from .gameplay_fields import identity
from .weapon_rates import prop

PS_CLASS = '/Script/OakGame.OakPlayerState'
EXP_ENTRY = '/Script/OakGame.PlayerExperienceState'
GLOBALS_EXP = '/Script/OakGame.OakGlobalsExperience'
AWARD_KILL_PATH = '/Script/OakGame.OakExperienceStatics:AwardKillExperienceToParty'
AWARD_KILL_SIG = (
    ('ContextActor', 'ZObjectProperty'),
    ('OptionalKiller', 'ZObjectProperty'),
)
PROGRESSION_TRACKS = {
    'oak2_characterxp_progression': 'character',
    'oak2_specializationxp_progression': 'specialization',
    'oak2_vaultcardxp_progression': 'vaultcard',
}
XP_ATTRIBUTES = (
    ('difficulty_combat_xp', 'Att_PlayerDifficulty_CombatXP_Multiplier', 'pc'),
    ('contract_xp_multiplier', 'Att_ContractRewards_Experience_Multiplier', 'pawn'),
    ('enemy_xp_formula', 'Att_Calc_EnemyExperienceFormula', 'pawn'),
)
SENTINEL = -123456.0


def _read_sname_token(entry, field_name):
    """Validate typed FSName struct descriptor and extract exact canonical token."""
    desc = prop(entry._type, field_name, 'ZStructProperty')
    if str(desc.Struct.Name) != 'SName':
        raise ValueError('unexpected FSName descriptor on ' + field_name)
    val = getattr(entry, field_name)
    val_type = getattr(val, '_type', None)
    if val is None or val_type is None or identity(val_type) != identity(desc.Struct):
        raise ValueError('unexpected FSName wrapper on ' + field_name)
    raw = getattr(val, 'Name', None)
    if raw is None:
        raw = str(val)
    token = str(raw).strip().lower()
    if not token or token == 'none':
        raise ValueError('empty FSName token on ' + field_name)
    return token


def _int_field(entry, name):
    val = getattr(entry, name)
    if type(val) is not int or val < 0:
        raise ValueError('invalid integer experience field: ' + name)
    return val


def snapshot_experience(ps):
    """Return an immutable dict of unique progression track -> experience state snapshot."""
    if ps is None or ps.Class._path_name() != PS_CLASS or 'Default__' in ps._path_name():
        raise ValueError('exact local OakPlayerState required')
    desc = prop(ps.Class, 'ExperienceState', 'ZArrayProperty')
    inner = desc.Inner
    if type(inner).__name__ != 'ZStructProperty' or inner.Struct._path_name() != EXP_ENTRY:
        raise ValueError('unexpected ExperienceState array schema')
    arr = ps.ExperienceState
    count = len(arr)
    if not 0 < count <= 32:
        raise ValueError('empty or oversized ExperienceState array')
    rows = {}
    for entry in arr:
        if entry._type._path_name() != EXP_ENTRY or identity(entry._type) != identity(inner.Struct):
            raise ValueError('unexpected FPlayerExperienceState wrapper')
        prop(entry._type, 'ExperienceLevel', 'ZIntProperty')
        prop(entry._type, 'ExperiencePoints', 'ZUInt64Property')
        prop(entry._type, 'ExperiencePointsRequiredForPreviousLevel', 'ZUInt64Property')
        prop(entry._type, 'ExperiencePointsRequiredForNextLevel', 'ZUInt64Property')
        prop(entry._type, 'bIsUnlocked', 'ZBoolProperty')
        unlocked = entry.bIsUnlocked
        if type(unlocked) is not bool:
            raise ValueError('invalid bIsUnlocked flag')
        token = _read_sname_token(entry, 'ExperienceId')
        track = PROGRESSION_TRACKS.get(token, token)
        if track in rows:
            raise ValueError('duplicate progression track: ' + track)
        rows[track] = {
            'id_token': token,
            'level': _int_field(entry, 'ExperienceLevel'),
            'points': _int_field(entry, 'ExperiencePoints'),
            'prev_req': _int_field(entry, 'ExperiencePointsRequiredForPreviousLevel'),
            'next_req': _int_field(entry, 'ExperiencePointsRequiredForNextLevel'),
            'unlocked': unlocked,
        }
    return rows


def inspect_globals_experience(globals_obj):
    """Read-only inspection of FOakGlobalsExperience.CombatExperienceModifier FGbxDefPtr."""
    if globals_obj is None or globals_obj._type._path_name() != GLOBALS_EXP:
        raise ValueError('exact OakGlobalsExperience struct required')
    prop(globals_obj._type, 'CombatExperienceModifier', 'ZGbxDefPtrProperty')
    mod_ptr = globals_obj.CombatExperienceModifier
    if type(mod_ptr).__name__ != 'FGbxDefPtr' or not isinstance(getattr(mod_ptr, '_name', None), str):
        raise ValueError('unresolved CombatExperienceModifier FGbxDefPtr')
    return mod_ptr._name


def read_xp_attributes(get_attr, pc, pawn):
    """Read-only diagnostic readback of native XP consumer attributes."""
    out = {}
    for key, attr_name, target in XP_ATTRIBUTES:
        ctx = pc if target == 'pc' else pawn
        try:
            val = get_attr(attr_name, ctx, SENTINEL)
            if type(val) in (int, float) and math.isfinite(val) and val != SENTINEL:
                out[key] = float(val)
            else:
                out[key] = None
        except Exception:
            out[key] = None
    return out


def bind_award_kill_xp(functions):
    """Verify exact AwardKillExperienceToParty signature before installing a read-only hook."""
    matches = [f for f in functions if f._path_name() == AWARD_KILL_PATH]
    if len(matches) != 1:
        raise ValueError('AwardKillExperienceToParty missing or ambiguous')
    fn = matches[0]
    ps = tuple(fn._properties())
    if (fn.Outer._path_name() != '/Script/OakGame.OakExperienceStatics'
            or fn.NumParams != len(AWARD_KILL_SIG)
            or tuple((str(p.Name), type(p).__name__) for p in ps) != AWARD_KILL_SIG
            or any(p.ArrayDim != 1 for p in ps)):
        raise ValueError('AwardKillExperienceToParty signature mismatch')
    return fn


class KillExperienceObserver:
    """Strictly read-only PRE/POST observer for matched AwardKillExperienceToParty calls."""

    def __init__(self, context, clock, thread, *, max_events=32, max_call_elapsed=2.0):
        self.context = context
        self.clock = clock
        self.thread = thread
        self.max_call_elapsed = float(max_call_elapsed)
        self.pending = None
        self._busy = False
        self.events = deque(maxlen=int(max_events))

    def _call_key(self, obj, args):
        obj_id = identity(obj) if obj is not None else None
        ctx = getattr(args, 'ContextActor', None)
        killer = getattr(args, 'OptionalKiller', None)
        if ctx is None:
            raise ValueError('missing ContextActor')
        return obj_id, identity(ctx), (identity(killer) if killer is not None else None)

    def on_pre(self, obj, args):
        # Always clear stale pending before any early return; reject nested calls.
        if self._busy:
            self.pending = None
            return
        self.pending = None
        self._busy = True
        try:
            pc, pawn, state, ok = self.context()
            if ok is not True:
                return
            call_key = self._call_key(obj, args)
            if call_key[2] is not None and call_key[2] != identity(pc):
                return
            before = snapshot_experience(state)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.clock(),
                call_key,
                before,
            )
        except Exception:
            self.pending = None
        finally:
            self._busy = False

    def on_post(self, obj, args):
        if self._busy:
            self.pending = None
            return
        pending = self.pending
        self.pending = None
        if pending is None:
            return
        self._busy = True
        try:
            scope_ids, tid, at, expected_key, before = pending
            now = self.clock()
            if now < at or (now - at) > self.max_call_elapsed:
                return
            if self._call_key(obj, args) != expected_key:
                return
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids):
                return
            after = snapshot_experience(state)
            if set(after) != set(before):
                return
            deltas = {}
            for track, row in after.items():
                prev = before[track]
                deltas[track] = {
                    'delta_points': row['points'] - prev['points'],
                    'delta_level': row['level'] - prev['level'],
                    'points': row['points'],
                    'level': row['level'],
                }
            self.events.append({'at': at, 'deltas': deltas})
        except Exception:
            return
        finally:
            self._busy = False

    def report_lines(self, get_attr=None, globals_obj=None):
        lines = ['Native XP Consumer & Kill Delta Observer (Read-Only):']
        if globals_obj is not None:
            try:
                lines.append('  OakGlobalsExperience.CombatExperienceModifier=' + inspect_globals_experience(globals_obj))
            except Exception as exc:
                lines.append('  OakGlobalsExperience unavailable: ' + str(exc)[:80])
        try:
            pc, pawn, state, ok = self.context()
            if ok is True:
                snap = snapshot_experience(state)
                for track in sorted(snap):
                    r = snap[track]
                    lines.append(
                        f'  Track={track}; Level={r["level"]}; Points={r["points"]}; '
                        f'NextReq={r["next_req"]}; Unlocked={r["unlocked"]}'
                    )
                if get_attr is not None:
                    attrs = read_xp_attributes(get_attr, pc, pawn)
                    for k, v in attrs.items():
                        lines.append(f'  Attr={k}; Value={v!r}')
        except Exception as exc:
            lines.append('  Snapshot unavailable: ' + str(exc)[:100])
        lines.append(f'  Observed kill XP events: {len(self.events)} (no writes, grants or replays)')
        return lines
