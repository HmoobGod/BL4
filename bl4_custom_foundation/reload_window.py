"""Experimental transaction around an existing reflected reload request.
Never invokes, blocks, replaces, or replays the request. No timer or ammo write.
"""
from .gameplay_fields import identity
from .session_control import Controller
from .weapon_rates import active_weapon, mode
from .reload_assist import REQUEST, REQUEST_SIG


def request_function(sdk):
    matches = [f for f in sdk.find_all('Function', exact=False)
               if str(f.Name) == 'ServerStartReloading' and f._path_name() == REQUEST]
    if len(matches) != 1:
        raise ValueError('reload request missing or ambiguous')
    fn = matches[0]
    props = tuple(fn._properties())
    if (fn.Outer._path_name() != REQUEST.rsplit(':',1)[0] or fn.NumParams != 2
            or tuple((str(p.Name),type(p).__name__) for p in props) != REQUEST_SIG
            or any(p.ArrayDim != 1 for p in props)):
        raise ValueError('reload request signature mismatch')
    return fn


class WindowController(Controller):
    def __init__(self, context, weak, report, thread, peer_tokens):
        super().__init__(context,weak,report,thread)
        self.peer_tokens=peer_tokens

    def capture(self,key):
        record=super().capture(key)
        if set(record['tokens']).intersection(self.peer_tokens()):
            raise ValueError('reload field already owned by another feature')
        return record


class ReloadWindow:
    def __init__(self, context, weak, permitted, thread, clock, report, peer_tokens=lambda: ()):
        self.context, self.weak, self.permitted = context, weak, permitted
        self.thread, self.clock, self.report = thread, clock, report
        self.peer_tokens=peer_tokens
        self.controller = None
        self.root = None
        self.depth = 0
        self.applying = False
        self.busy = False
        self.fault = False
        self.disabled = False
        self.last_reason = ''
        self.last_result = 'Waiting for native reload request'

    def note(self, reason):
        self.last_result = reason
        if reason != self.last_reason:
            self.last_reason = reason
            self.report('RELOAD EVENT: '+reason)

    def guarded_context(self):
        pc,pawn,state,ok = self.context()
        if self.applying:
            try:
                w = active_weapon(pawn)
                ok = (ok and self.permitted() and self.thread() == self.root[0]
                      and identity(w) == self.root[1] and mode(w) == self.root[2])
            except Exception:
                ok = False
        return pc,pawn,state,ok

    def pre(self, obj, args, selection):
        # Count all nested invocations on the root thread, even foreign weapons.
        if self.root is not None:
            if self.thread() == self.root[0]: self.depth += 1
            return
        if self.busy or self.fault or self.disabled or not self.permitted(): return
        self.busy = True
        try:
            pc,pawn,state,ok = self.context()
            w = active_weapon(pawn)
            if not ok or identity(w) != identity(obj): return
            index, flags = args.UseModeIndex, args.Flags_0
            if type(index) is not int or index != mode(w) or type(flags) is not int or flags != 0:
                self.note('local request mode or flags unsupported; native request unchanged')
                return
            if str(w.CurrentState) != 'Active':
                self.note('local request weapon not idle; native request unchanged')
                return
            self.root = (self.thread(), identity(w), index, self.clock(), selection)
            self.depth = 1
            self.applying = True
            self.controller = WindowController(self.guarded_context,self.weak,self.report,self.thread,self.peer_tokens)
            if not self.controller.activate('reload', selection):
                self.note('admission rejected; native request unchanged')
            elif 'reload' in self.controller.records:
                self.note('duration applied before native request; gameplay unverified')
        except Exception as exc:
            self.note('admission unavailable: '+str(exc)[:100])
        finally:
            self.applying = False
            self.busy = False
            if self.controller is not None and self.controller.fault:
                self.fault = True
            # Keep pairing state even when activation failed: no second apply on nested request.

    def finish(self, reason):
        if self.busy or self.root is None or self.thread() != self.root[0]: return
        self.busy = True
        try:
            had_record = bool(self.controller is not None and self.controller.records)
            if had_record:
                if not self.controller.restore_all(reason):
                    self.fault = True
            if self.controller is not None and self.controller.fault:
                self.fault = True
            if self.fault:
                self.last_result = 'FAULT / exit game'
            if not self.fault and (had_record or reason != 'reload request returned'):
                self.note('native request returned; original duration restored' if reason == 'reload request returned' else reason)
        except Exception:
            self.fault = True
            raise
        finally:
            self.root = None
            self.depth = 0
            self.busy = False

    def post(self, obj):
        if self.root is None or self.thread() != self.root[0]: return
        if self.depth > 1:
            self.depth -= 1
            return
        if self.busy or identity(obj) != self.root[1]: return
        self.finish('reload request returned')

    def watchdog(self):
        # A lost post callback must not leave an indefinite modified value.
        # Disable this experiment for the process after watchdog cleanup.
        if self.root is not None and not self.busy and self.thread() == self.root[0] and self.clock()-self.root[3] >= .5:
            self.disabled = True
            self.finish('post callback missing; experiment disabled until restart')
