"""Focused synthetic tests for R4 native return handling and cancellation admission."""
import unittest
from enum import IntEnum
from types import SimpleNamespace as NS
import test_batch


class Outcome(IntEnum):
    Success = 0
    Failure = 1


class Kind:
    Name = 'GbxAttributeDef'
    def _get_address(self): return id(self)


class Pointer:
    def __init__(self, name, kind):
        self._name, self._type, self.address = name, kind, 123
    def _get_address(self): return self.address


class ResultTests(unittest.TestCase):
    def setUp(self):
        fixture = test_batch.Batch(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        from native_progression_trial import NativeAPI, Trial
        self.Trial = Trial
        self.api = NativeAPI.__new__(NativeAPI)
        self.api.pointer, self.api.kind = Pointer, Kind()
        self.api.postadd, self.api.failure, self.api.success = 2, Outcome.Failure, Outcome.Success
        self.handle = NS(_type=NS(Name='GbxAttributeModifierHandle'))
        self.definition = Pointer('Att_CombatXP_Multiplier', self.api.kind)
        self.result = (self.handle, self.definition, Outcome.Success)
        self.calls = []
        self.api.library = NS(AddModifierToGbxAttribute=self.add)

    def add(self, *args):
        self.calls.append(args)
        return self.result

    def invoke(self):
        self.api.add('xp', object(), 1.)

    def test_three_values(self):
        self.invoke(); self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0]._name, 'Att_CombatXP_Multiplier')

    def test_two_values_rejected(self):
        self.result = (self.handle, Outcome.Success)
        with self.assertRaisesRegex(ValueError, 'shape'): self.invoke()
        self.assertEqual(len(self.calls), 1)

    def test_failure_rejected(self):
        self.result = (self.handle, self.definition, Outcome.Failure)
        with self.assertRaisesRegex(ValueError, 'outcome'): self.invoke()

    def test_wrong_definition_rejected(self):
        self.definition._name = 'Att_PickupCash_Multiplier'
        with self.assertRaisesRegex(ValueError, 'identity'): self.invoke()

    def test_wrong_handle_rejected(self):
        self.handle._type.Name = 'Unrelated'
        with self.assertRaisesRegex(ValueError, 'identity'): self.invoke()

    def test_wrong_type_identity_rejected(self):
        self.definition._type = Kind()
        with self.assertRaisesRegex(ValueError, 'identity'): self.invoke()

    def test_unresolved_rejected(self):
        self.definition.address = 0
        with self.assertRaises(ValueError): self.invoke()

    def test_untyped_outcome_rejected(self):
        self.result = (self.handle, self.definition, 0)
        with self.assertRaisesRegex(ValueError, 'outcome'): self.invoke()

    def trial(self):
        objects = [Kind(), Kind(), Kind()]
        objects[1].EquippedInventorySlots = NS(items=[NS(SourceItemHandle=NS(Handle=1), ReplicationID=1, ReplicationKey=1)])
        self.flags = NS(eligible=True, consent=True, value=1.)
        c = NS(context=lambda:(*objects, self.flags.eligible), thread=lambda:1,
               weak_pointer=lambda obj:lambda:obj, fault=False, stop_pending=None, log=lambda msg:True)
        c.fail = lambda msg:setattr(c, 'fault', True)
        def change(key, pawn, delta):
            self.flags.value += delta
            self.calls.append(delta)
        t = self.Trial(c, NS(read=lambda k,p:self.flags.value, add=change), lambda:self.flags.consent, 'xp')
        self.assertTrue(t.activate(2.))
        return t, c

    def test_inverse_after_consent_withdrawal(self):
        t, c = self.trial(); self.flags.consent = False; c.stop_pending = 'stop'
        self.assertTrue(t.cancel()); self.assertEqual(self.flags.value, 1.)
        self.assertEqual(self.calls, [1., -1.])

    def test_no_inverse_after_solo_lost(self):
        t, c = self.trial(); self.flags.eligible = False
        self.assertFalse(t.cancel()); self.assertTrue(c.fault)
        self.assertEqual(self.calls, [1.])
