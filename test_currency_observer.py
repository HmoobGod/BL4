"""Synthetic regression tests for read-only currency pickup & Eridium contradiction observer."""
import types
import unittest
from test_foundation import Test as FoundationTest


class Node(types.SimpleNamespace):
    def _get_address(self):
        return id(self)


def make_prop(name, cls_name, **extra):
    cls = type(cls_name, (), {})
    obj = cls()
    obj.Name = name
    obj.ArrayDim = 1
    for k, v in extra.items():
        setattr(obj, k, v)
    return obj


def make_type(path, props=()):
    return Node(_path_name=lambda: path, _properties=lambda: list(props), Name=path.rsplit('.', 1)[-1])


class CurrencyObserverTests(unittest.TestCase):
    def setUp(self):
        self._base = FoundationTest()
        self._base.setUp()
        self.addCleanup(self._base.doCleanups)
        from bl4_custom_foundation import currency_observer as C
        self.C = C
        self.tid = 77
        self.time = 50.0
        self.ok = True

        self.cur_t = make_type(C.CURRENCY_STRUCT, [make_prop('Amount', 'ZUInt64Property')])
        self.eridium_row = Node(_type=self.cur_t, type=Node(Name='eridium'), Amount=10)
        self.cash_row = Node(_type=self.cur_t, type=Node(Name='cash'), Amount=500)
        self.mgr_t = make_type(C.CURRENCY_MANAGER, [
            make_prop('currencies', 'ZArrayProperty', Inner=make_prop('currencies', 'ZStructProperty', Struct=self.cur_t)),
        ])
        self.mgr = Node(Class=self.mgr_t, _type=self.mgr_t, _path_name=lambda: '/Game/World.CurrencyMgr_0', currencies=[self.eridium_row, self.cash_row])
        self.pc = Node(_path_name=lambda: '/Game/World.OakPlayerController_0', CurrencyManager=self.mgr)
        self.pawn = Node(_path_name=lambda: '/Game/World.OakCharacter_0')
        self.state = Node(_path_name=lambda: '/Game/World.OakPlayerState_0')
        self.pickup_cls = make_type(C.PICKUP)
        self.bodies = {}
        self.attrs = {
            'eridium_held': 10.0, 'cash_held': 500.0,
            'calc_eridium_pickup': 2.0, 'calc_cash_pickup': 100.0,
            'Att_PickupEridium_Multiplier': 2.0, 'Att_PickupCash_Multiplier': 1.0,
        }

    def context(self):
        return self.pc, self.pawn, self.state, self.ok

    def make_pickup(self, body):
        p = Node(Class=self.pickup_cls, _type=self.pickup_cls, _path_name=lambda: '/Game/World.Pickup_0')
        self.bodies[id(p)] = body
        return p

    def test_snapshot_currencies_rejects_duplicates(self):
        snap = self.C.snapshot_currencies(self.pc)
        self.assertEqual(snap, {'eridium': 10, 'cash': 500})
        self.mgr.currencies.append(Node(_type=self.cur_t, type=Node(Name='eridium'), Amount=1))
        with self.assertRaises(ValueError):
            self.C.snapshot_currencies(self.pc)

    def test_observes_exact_eridium_pickup_delta_and_formulas(self):
        obs = self.C.CurrencyPickupObserver(
            self.context, lambda a: self.bodies.get(id(a)),
            lambda n, ctx, d: self.attrs.get(n, d),
            lambda: self.time, lambda: self.tid,
        )
        p = self.make_pickup(self.C.ERIDIUM_SINGLE_STACK_BODY)
        args = Node(OverlappedActor=p, OtherActor=self.pawn)
        obs.on_pre(p, args)
        # Simulate live game awarding +1 constant Eridium (distinguishing from calc_eridium_pickup=2.0 / calc_cash_pickup=100.0)
        self.eridium_row.Amount += 1
        obs.on_post(p, args)
        self.assertEqual(len(obs.events), 1)
        ev = obs.events[0]
        self.assertEqual(ev['pickup_kind'], 'eridium')
        self.assertEqual(ev['eridium_delta'], 1)
        self.assertEqual(ev['cash_delta'], 0)
        self.assertEqual(ev['calc_eridium_pickup'], 2.0)
        self.assertEqual(ev['calc_cash_pickup'], 100.0)

    def test_ignores_mismatched_post_and_foreign_actor(self):
        obs = self.C.CurrencyPickupObserver(
            self.context, lambda a: self.bodies.get(id(a)),
            lambda n, ctx, d: self.attrs.get(n, d),
            lambda: self.time, lambda: self.tid,
        )
        p = self.make_pickup(self.C.ERIDIUM_SINGLE_STACK_BODY)
        # Foreign actor ignored
        obs.on_pre(p, Node(OverlappedActor=p, OtherActor=Node()))
        self.assertIsNone(obs.pending)
        # Mismatched pickup on POST ignored
        p2 = self.make_pickup(self.C.CASH_SINGLE_STACK_BODY)
        obs.on_pre(p, Node(OverlappedActor=p, OtherActor=self.pawn))
        self.eridium_row.Amount += 5
        obs.on_post(p2, Node(OverlappedActor=p2, OtherActor=self.pawn))
        self.assertEqual(len(obs.events), 0)


if __name__ == '__main__':
    unittest.main()
