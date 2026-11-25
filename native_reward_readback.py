"""R11 source-only one-callback readback trial; NOT a loadable mod.
No hook registration, imports of game modules, or automatic execution.
Call only from a separately reviewed, explicitly authorized game-thread entrypoint.
"""
import threading

from native_progression_trial import NativeAPI, Trial

_used = False
CONFIRM = 'DISPOSABLE OFFLINE CASH READBACK ONLY'


def run_cash_readback(foundation, sdk, confirmation):
    """One cash 1->2->1 readback attempt, with no gameplay between calls.

    The caller must be inside the verified camera callback, on a fresh game
    launch with a disposable character, network disconnected and all other
    tuning inactive. This module is not wired to any runtime entrypoint.
    A result of cancelled is net readback, never proof of native removal.
    Do not reload this module or retry after any attempt; exit the game.
    """
    global _used
    if confirmation != CONFIRM or _used:
        return 'refused'
    _used = True
    try:
        hooks = sdk.hooks
        if (foundation._monitor_thread != threading.get_ident()
                or not foundation._valid_test_backend()
                or not foundation._monitor_registered
                or hooks.has_hook(foundation._MONITOR_PATH, hooks.Type.POST_UNCONDITIONAL,
                                  foundation._MONITOR_ID) is not True
                or foundation.mod.is_enabled is not True
                or foundation.auto_master.value is not False
                or foundation._auto_owned or foundation._activation_request is not None
                or foundation.conflicting_mods()):
            return 'preflight-refused'
        previous = foundation._controller
        if previous is not None and (previous.records or previous.fault or previous.busy
                                     or previous.stop_pending is not None):
            return 'preflight-refused'
        session_api = foundation.bound_session(sdk)

        def strict_context():
            pc, pawn, state, eligible = foundation.current_session(session_api)
            # Existing one-player gate permits a non-standalone host. This trial does not.
            strict = eligible is True and session_api[0](pawn) is True
            return pc, pawn, state, strict

        if strict_context()[3] is not True:
            return 'preflight-refused'
        controller = foundation.Controller(strict_context, sdk.unreal.WeakPointer,
                                           foundation.report_live, threading.get_ident)
        native = NativeAPI(sdk)
        trial = Trial(controller, native, lambda: confirmation == CONFIRM, 'cash')
        if not trial.activate(2.0):
            return 'fault-exit' if controller.fault else 'preflight-refused'
        # Same callback: do not yield, wait, collect cash, or change equipment.
        if not trial.cancel():
            return 'fault-exit'
        return 'cancelled-exit'
    except Exception as exc:
        foundation.report_live('CASH READBACK HOLD: ' + type(exc).__name__ + '; exit game; no retry')
        return 'fault-exit'
