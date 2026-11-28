"""Synthetic regression tests for read-only native XP observer (zero writes/grants)."""
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


class XPObserverTests(unittest.TestCase):
    def setUp(self):
        self._base = FoundationTest()
        self._base.setUp()
        self.addCleanup(self._base.doCleanups)
        from bl4_custom_foundation import xp_observer as X
        self.X = X
        self.tid = 55
        self.time = 100.0
        self.ok = True

        self.entry_t = make_type(X.EXP_ENTRY, [
            make_prop('ExperienceLevel', 'ZIntProperty'),
            make_prop('ExperiencePoints', 'ZUInt64Property'),
            make_prop('ExperiencePointsRequiredForPreviousLevel', 'ZUInt64Property'),
            make_prop('ExperiencePointsRequiredForNextLevel', 'ZUInt64Property'),
            make_prop('bIsUnlocked', 'ZBoolProperty'),
        ])
        self.char_entry = Node(
            _type=self.entry_t,
            ExperienceLevel=32,
            ExperiencePoints=125000,
            ExperiencePointsRequiredForPreviousLevel=110000,
            ExperiencePointsRequiredForNextLevel=140000,
            ExperienceId='oak2_characterxp_progression',
            bIsUnlocked=True,
        )
        self.spec_entry = Node(
            _type=self.entry_t,
            ExperienceLevel=14,
            ExperiencePoints=42000,
            ExperiencePointsRequiredForPreviousLevel=35000,
            ExperiencePointsRequiredForNextLevel=50000,
            ExperienceId='oak2_specializationxp_progression',
            bIsUnlocked=True,
        )
        self.ps_t = make_type(X.PS_CLASS, [
            make_prop('ExperienceState', 'ZArrayProperty', Inner=make_prop('ExperienceState', 'ZStructProperty', Struct=self.entry_t)),
        ])
        self.ps = Node(
            Class=self.ps_t,
            _type=self.ps_t,
            _path_name=lambda: '/Game/World.OakPlayerState_0',
            ExperienceState=[self.char_entry, self.spec_entry],
        )
        self.pc = Node(_path_name=lambda: '/Game/World.OakPlayerController_0')
        self.pawn = Node(_path_name=lambda: '/Game/World.OakCharacter_0')

        outer = Node(_path_name=lambda: '/Script/OakGame.OakExperienceStatics')
        self.award_fn = Node(
            Name='AwardKillExperienceToParty',
            Outer=outer,
            NumParams=2,
            _path_name=lambda: X.AWARD_KILL_PATH,
            _properties=lambda: [
                make_prop('ContextActor', 'ZObjectProperty'),
                make_prop('OptionalKiller', 'ZObjectProperty'),
            ],
        )

    def context(self):
        return self.pc, self.pawn, self.ps, self.ok

    def test_snapshot_distinguishes_character_and_specialization_xp(self):
        snap = self.X.snapshot_experience(self.ps)
        self.assertEqual(snap['character']['level'], 32)
        self.assertEqual(snap['character']['points'], 125000)
        self.assertEqual(snap['specialization']['level'], 14)
        self.assertEqual(snap['specialization']['points'], 42000)

    def test_bind_award_kill_xp_validates_exact_signature(self):
        fn = self.X.bind_award_kill_xp([self.award_fn])
        self.assertIs(fn, self.award_fn)
        bad = Node(Name='AwardKillExperienceToParty', Outer=self.award_fn.Outer, NumParams=1, _path_name=lambda: self.X.AWARD_KILL_PATH, _properties=lambda: [])
        with self.assertRaises(ValueError):
            self.X.bind_award_kill_xp([bad])

    def test_kill_observer_records_exact_deltas_without_writes(self):
        obs = self.X.KillExperienceObserver(self.context, lambda: self.time, lambda: self.tid)
        args = Node(ContextActor=Node(), OptionalKiller=self.pc)
        obs.on_pre(None, args)
        # Simulate native kill award
        self.char_entry.ExperiencePoints += 450
        self.spec_entry.ExperiencePoints += 450
        obs.on_post(None, args)
        self.assertEqual(len(obs.events), 1)
        deltas = obs.events[0]['deltas']
        self.assertEqual(deltas['character']['delta_points'], 450)
        self.assertEqual(deltas['specialization']['delta_points'], 450)

    def test_kill_observer_ignores_foreign_killer(self):
        obs = self.X.KillExperienceObserver(self.context, lambda: self.time, lambda: self.tid)
        foreign_pc = Node(_path_name=lambda: '/Game/World.OakPlayerController_1')
        args = Node(ContextActor=Node(), OptionalKiller=foreign_pc)
        obs.on_pre(None, args)
        self.char_entry.ExperiencePoints += 450
        obs.on_post(None, args)
        self.assertEqual(len(obs.events), 0)

    def test_read_xp_attributes_and_report_lines(self):
        values = {
            'Att_PlayerDifficulty_CombatXP_Multiplier': 0.4,
            'Att_ContractRewards_Experience_Multiplier': 2.0,
            'Att_Calc_EnemyExperienceFormula': 260.0,
        }
        get_attr = lambda name, ctx, default: values.get(name, default)
        attrs = self.X.read_xp_attributes(get_attr, self.pc, self.pawn)
        self.assertEqual(attrs['difficulty_combat_xp'], 0.4)
        self.assertEqual(attrs['contract_xp_multiplier'], 2.0)
        self.assertEqual(attrs['enemy_xp_formula'], 260.0)
        obs = self.X.KillExperienceObserver(self.context, lambda: self.time, lambda: self.tid)
        lines = obs.report_lines(get_attr=get_attr)
        text = '\n'.join(lines)
        self.assertIn('Track=character', text)
        self.assertIn('Track=specialization', text)
        self.assertIn('Attr=difficulty_combat_xp; Value=0.4', text)


if __name__ == '__main__':
    unittest.main()
