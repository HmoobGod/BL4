"""Unregistered, source-only lifecycle for the disposable inventory readback.

SDK v1.10.0 hook.cpp (1f9fccda3d28b23282a06bf3b420a7daa4213501):
add_hook/has_hook/remove_hook return booleans. Do not remove from inside the
callback. No import of the SDK, no automatic registration or loader entrypoint.
Explicit registration still requires separate native authorization.
"""
import threading
from inventory_admission import OneShot, PATH

HOOK_ID = 'bl4_custom_inventory_capacity_source_v2'


class Registration:
    def __init__(self):
        self.shot = OneShot()
        self.sdk = None
        self.thread = None
        self.owned = False
        self.active = False
        self.cleaned = False
        self.disabled = False
        self.status = 'unregistered'

    def _key(self):
        return PATH, self.sdk.hooks.Type.POST_UNCONDITIONAL, HOOK_ID

    def attach(self, kind, confirmation):
        """Explicit source integration only; never invoked on import."""
        if self.disabled or self.owned or self.active or self.thread is not None:
            return False
        if not self.shot.arm(kind, confirmation):
            return False
        _, self.sdk, _, self.thread, _ = self.shot.pending
        try:
            key = self._key()
            if self.sdk.hooks.has_hook(*key) is not False:
                raise RuntimeError('hook identifier already present or uncertain')
            if self.sdk.hooks.add_hook(*key, self.callback) is not True:
                # The SDK has not acknowledged ownership. Never remove an
                # unknown registration; pending callback is made inert below.
                raise RuntimeError('registration not acknowledged')
            self.owned = True
            if self.sdk.hooks.has_hook(*key) is not True:
                raise RuntimeError('registration readback failed')
            self.status = 'armed'
            return True
        except Exception as exc:
            self.shot.disarm()
            self.disabled = True
            self.status = 'HOLD: ' + str(exc) + '; no retry'
            return False

    def callback(self, camera, args, ret, func):
        # Never execute after disable or uncertain registration. Even nested
        # callbacks or repeated calls after a completed probe are inert.
        if self.disabled or not self.owned or self.active or self.shot.pending is None:
            return None
        self.active = True
        try:
            if self.sdk.hooks.has_hook(*self._key()) is not True:
                self.shot.disarm()
                self.shot.status = 'HOLD: registered hook missing; no retry'
                return None
            return self.shot.callback(camera, args, ret, func)
        except Exception as exc:
            self.shot.disarm()
            self.shot.status = 'HOLD: callback lifecycle failure: ' + str(exc) + '; no retry'
            return None
        finally:
            self.active = False
            self.disabled = True
            self.status = self.shot.status + '; cleanup required outside callback'

    def disable(self):
        """Cancel pending, then remove only an acknowledged registration.

        Must run on the original game thread outside the callback; on a cleanup
        failure retain ownership for inspection, never rearm or claim success.
        """
        if self.active or (self.thread is not None and threading.get_ident() != self.thread):
            return False
        self.disabled = True
        self.shot.disarm()
        if not self.owned:
            return self.cleaned or self.thread is None  # uncertain registration is not a clean receipt
        try:
            key = self._key()
            if self.sdk.hooks.has_hook(*key) is not True:
                raise RuntimeError('owned hook identity unavailable')
            if self.sdk.hooks.remove_hook(*key) is not True:
                raise RuntimeError('hook removal not acknowledged')
            if self.sdk.hooks.has_hook(*key) is not False:
                raise RuntimeError('hook removal readback failed')
            self.owned = False
            self.cleaned = True
            self.status = 'disabled; no retry'
            return True
        except Exception as exc:
            self.status = 'HOLD: cleanup failed: ' + str(exc) + '; exit session'
            return False
