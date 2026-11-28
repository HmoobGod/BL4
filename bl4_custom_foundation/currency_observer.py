"""Read-only native currency pickup & Eridium consumer contradiction observer.

Strictly read-only diagnostic module: NEVER calls GiveCurrency, Server_AddCurrency,
or mutates blackboard/shared currency definitions.

Resolves the decoded bl4db.json Eridium contradiction on live pickups by recording
exact before/after CurrencyManager balances (eridium vs cash) and live formula
readbacks (calc_eridium_pickup vs calc_cash_pickup) on matched AInventoryPickup
OnActorOverlap callbacks for exact ERIDIUM_SINGLE_STACK_BODY / CASH_SINGLE_STACK_BODY.
"""
from collections import deque
import math
from .gameplay_fields import identity
from .loot_vacuum import CASH_SINGLE_STACK_BODY, ERIDIUM_SINGLE_STACK_BODY, PICKUP
from .weapon_rates import prop

CURRENCY_MANAGER = '/Script/GbxGame.GbxCurrencyManager'
CURRENCY_STRUCT = '/Script/GbxGame.GbxCurrency'
OVERLAP_PATH = '/Script/GbxGame.InventoryPickup:OnActorOverlap'
OVERLAP_SIG = (
    ('OverlappedActor', 'ZObjectProperty'),
    ('OtherActor', 'ZObjectProperty'),
)
SENTINEL = -123456.0


def _token_name(tok):
    if tok is None:
        raise ValueError('missing FSToken')
    raw = getattr(tok, 'Name', None)
    if raw is None:
        raw = str(tok)
    name = str(raw).strip().lower()
    if not name or name == 'none':
        raise ValueError('empty FSToken')
    return name


def snapshot_currencies(pc):
    """Read immutable {currency_token: amount_int} from GbxPlayerController.CurrencyManager."""
    mgr = getattr(pc, 'CurrencyManager', None)
    if mgr is None or mgr.Class._path_name() != CURRENCY_MANAGER or 'Default__' in mgr._path_name():
        raise ValueError('local GbxCurrencyManager unavailable')
    desc = prop(mgr.Class, 'currencies', 'ZArrayProperty')
    inner = desc.Inner
    if type(inner).__name__ != 'ZStructProperty' or inner.Struct._path_name() != CURRENCY_STRUCT:
        raise ValueError('unexpected currencies array schema')
    out = {}
    for entry in mgr.currencies:
        if entry._type._path_name() != CURRENCY_STRUCT or identity(entry._type) != identity(inner.Struct):
            raise ValueError('unexpected FGbxCurrency wrapper')
        prop(entry._type, 'Amount', 'ZUInt64Property')
        amt = entry.Amount
        if type(amt) is not int or amt < 0:
            raise ValueError('invalid currency amount')
        tok = _token_name(getattr(entry, 'type', None))
        if tok in out:
            raise ValueError('duplicate currency token: ' + tok)
        out[tok] = amt
    return out


def read_currency_formulas(get_attr, pc, pawn):
    """Read-only snapshot of live eridium_held, cash_held, calc_eridium_pickup, calc_cash_pickup."""
    specs = (
        ('eridium_held', pc),
        ('cash_held', pc),
        ('calc_eridium_pickup', pawn),
        ('calc_cash_pickup', pawn),
        ('Att_PickupEridium_Multiplier', pawn),
        ('Att_PickupCash_Multiplier', pawn),
    )
    out = {}
    for name, ctx in specs:
        try:
            v = get_attr(name, ctx, SENTINEL)
            out[name] = float(v) if type(v) in (int, float) and math.isfinite(v) and v != SENTINEL else None
        except Exception:
            out[name] = None
    return out


class CurrencyPickupObserver:
    """Strictly read-only PRE/POST observer for ordinary Eridium/Cash pickup overlaps."""

    def __init__(self, context, body_reader, get_attr, clock, thread, *, max_events=32, max_call_elapsed=2.0):
        self.context = context
        self.body_reader = body_reader
        self.get_attr = get_attr
        self.clock = clock
        self.thread = thread
        self.max_call_elapsed = float(max_call_elapsed)
        self.pending = None
        self._busy = False
        self.events = deque(maxlen=int(max_events))

    def _pickup_kind(self, actor):
        if actor is None or actor.Class._path_name() != PICKUP or 'Default__' in actor._path_name():
            return None
        body = self.body_reader(actor)
        if body == ERIDIUM_SINGLE_STACK_BODY:
            return 'eridium'
        if body == CASH_SINGLE_STACK_BODY:
            return 'cash'
        return None

    def on_pre(self, obj, args):
        if self._busy:
            self.pending = None
            return
        self.pending = None
        self._busy = True
        try:
            pc, pawn, state, ok = self.context()
            if ok is not True:
                return
            overlapped = getattr(args, 'OverlappedActor', None)
            other = getattr(args, 'OtherActor', None)
            if other is None or identity(other) != identity(pawn):
                return
            pickup = overlapped if overlapped is not None else obj
            kind = self._pickup_kind(pickup)
            if kind is None:
                return
            balances_before = snapshot_currencies(pc)
            formulas = read_currency_formulas(self.get_attr, pc, pawn)
            self.pending = (
                (identity(pc), identity(pawn), identity(state)),
                self.thread(),
                self.clock(),
                (identity(obj), identity(pickup), identity(other)),
                kind,
                balances_before,
                formulas,
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
            scope_ids, tid, at, expected_key, kind, before, formulas = pending
            now = self.clock()
            if now < at or (now - at) > self.max_call_elapsed:
                return
            overlapped = getattr(args, 'OverlappedActor', None)
            other = getattr(args, 'OtherActor', None)
            pickup = overlapped if overlapped is not None else obj
            if other is None or (identity(obj), identity(pickup), identity(other)) != expected_key:
                return
            pc, pawn, state, ok = self.context()
            if (ok is not True or self.thread() != tid
                    or (identity(pc), identity(pawn), identity(state)) != scope_ids):
                return
            after = snapshot_currencies(pc)
            eridium_delta = after.get('eridium', 0) - before.get('eridium', 0)
            cash_delta = after.get('cash', 0) - before.get('cash', 0)
            if eridium_delta == 0 and cash_delta == 0:
                return
            self.events.append({
                'at': at,
                'pickup_kind': kind,
                'eridium_delta': eridium_delta,
                'cash_delta': cash_delta,
                'calc_eridium_pickup': formulas.get('calc_eridium_pickup'),
                'calc_cash_pickup': formulas.get('calc_cash_pickup'),
            })
        except Exception:
            return
        finally:
            self._busy = False
