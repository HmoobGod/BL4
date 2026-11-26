"""Offline-only prototype for the native Start/StopHealthRegen ID lifetime.
Not imported by the SDKMOD. No game bindings, tag construction, or rate guessing.
A future bridge must establish the local pawn, exact health-only tags, initializer,
and native ID validity. Bounded duration is defense in depth, not proof of cleanup.
"""
import math


class Lease:
    def __init__(self, admit, start, stop, valid_id):
        self.admit, self.start, self.stop, self.valid_id = admit, start, stop, valid_id
        self.record = None
        self.fault = False

    def begin(self, duration, tick):
        if self.record is not None or self.fault:
            return False
        if (type(duration) not in (int, float) or type(tick) not in (int, float)
                or not math.isfinite(duration) or not math.isfinite(tick)
                or not .25 <= tick <= 1 or not tick <= duration <= 5):
            return False
        # Admission supplies an exact original actor, stable identity, constructed
        # health-only tags and initialized rate. No raw values are synthesized here.
        try:
            context = self.admit()
            if context is None:
                return False
            pawn, identity, rate, tags = context
            if pawn is None or identity is None or rate is None or tags is None:
                return False
        except Exception:
            return False
        try:
            handle = self.start(pawn, duration, rate, True, tick, tags)
            if type(handle) is not int or not self.valid_id(handle):
                self.fault = True
                return False
        except Exception:
            # A call that raises may already have started native regeneration.
            self.fault = True
            return False
        self.record = (identity, handle)
        return True

    def cancel(self, original):
        if self.record is None:
            return not self.fault
        identity, handle = self.record
        try:
            # Separate restoration resolver, not a new activation/admission check.
            pawn, current = original()
            if pawn is None or current != identity:
                raise ValueError('original pawn unavailable')
            self.stop(pawn, handle)
        except Exception:
            self.fault = True
            return False
        self.record = None
        # Native stop returns void; only dispatch is known, not cancellation.
        return not self.fault
