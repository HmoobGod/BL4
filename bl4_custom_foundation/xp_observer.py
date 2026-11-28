"""Read-only native XP progression and kill-award telemetry observer.

Strictly read-only diagnostic module: NEVER grants XP, NEVER calls
BP_SetExperienceLevel, NEVER mutates shared difficulty tables, NEVER writes
ExperienceState, and NEVER replays AwardKillExperienceToParty.

Grounded in pinned historical SDK declarations
(F100rwater/borderlands4_SDK_Dumper7 a958797d4dc51ff56ec0891db0039591abb58a9a)
and decoded community NCS metadata (lagarrueal/borderlands4-save-editor bl4db.json):
- OakPlayerState.ExperienceState (TArray<FPlayerExperienceState>)
- OakExperienceStatics.AwardKillExperienceToParty(ContextActor, OptionalKiller)
- Att_PlayerDifficulty_CombatXP_Multiplier (PlayerDifficultyDataTableValueResolver)
- Att_ContractRewards_Experience_Multiplier (GbxConstantAttributeValueResolver)
- Att_Calc_EnemyExperienceFormula (BalanceFormulaValueResolver)
"""
from collections import deque
import math
from .gameplay_fields import identity
from .weapon_rates import prop

PS_CLASS = '/Script/OakGame.OakPlayerState'
EXP_ENTRY = '/Script/OakGame.PlayerExperienceState'
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


def classify_track(raw_id):
    text = str(raw_id or '').strip().lower()
    for token, label in PROGRESSION_TRACKS.items():
        if token in text:
            return label
    return text or 'unknown'


def _int_field(entry, name):
    val = getattr(entry, name)
    if type(val) is not int or val < 0:
        raise ValueError('invalid integer experience field: ' + name)
    return val


def snapshot_experience(ps):
    """Return an immutable dict of progression track -> experience state snapshot."""
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
        track = classify_track(getattr(entry, 'ExperienceId', ''))
        rows[track] = {
            'level': _int_field(entry, 'ExperienceLevel'),
            'points': _int_field(entry, 'ExperiencePoints'),
            'prev_req': _int_field(entry, 'ExperiencePointsRequiredForPreviousLevel'),
            'next_req': _int_field(entry, 'ExperiencePointsRequiredForNextLevel'),
            'unlocked': unlocked,
        }
    return rows


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
    """Strictly read-only PRE/POST observer for AwardKillExperienceToParty deltas."""

    def __init__(self, context, clock, thread, *, max_events=32):
        self.context = context
        self.clock = clock
        self.thread = thread
        self.pending = None
        self.events = deque(maxlen=int(max_events))

    def on_pre(self, obj, args):
        try:
            pc, pawn, state, ok = self.context()
            if ok is not True:
                return
            killer = getattr(args, 'OptionalKiller', None)
            if killer is not None and identity(killer) != identity(pc):
                return
            before = snapshot_experience(state)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.clock(),
                before,
            )
        except Exception:
            self.pending = None

    def on_post(self, obj, args):
        if self.pending is None:
            return
        pending = self.pending
        self.pending = None
        try:
            scope_ids, tid, at, before = pending
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids):
                return
            after = snapshot_experience(state)
            deltas = {}
            for track, row in after.items():
                prev = before.get(track)
                if prev is not None:
                    deltas[track] = {
                        'delta_points': row['points'] - prev['points'],
                        'delta_level': row['level'] - prev['level'],
                        'points': row['points'],
                        'level': row['level'],
                    }
            self.events.append({'at': at, 'deltas': deltas})
        except Exception:
            return

    def report_lines(self, get_attr=None):
        lines = ['Native XP Consumer & Kill Delta Observer (Read-Only):']
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
