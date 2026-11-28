"""Synthetic regression tests for upgraded typed-FSName read-only XP observer."""
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

        self.sname_t = make_type('/Script/GbxCore.SName')
        self.entry_t = make_type(X.EXP_ENTRY, [
            make_prop('ExperienceLevel', 'ZIntProperty'),
            make_prop('ExperiencePoints', 'ZUInt64Property'),
            make_prop('ExperiencePointsRequiredForPreviousLevel', 'ZUInt64Property'),
            make_prop('ExperiencePointsRequiredForNextLevel', 'ZUInt64Property'),
            make_prop('ExperienceId', 'ZStructProperty', Struct=self.sname_t),
            make_prop('bIsUnlocked', 'ZBoolProperty'),
        ])
        self.char_entry = self.make_entry('oak2_characterxp_progression', 32, 125000, 110000, 140000)
        self.spec_entry = self.make_entry('oak2_specializationxp_progression', 14, 42000, 35000, 50000)
        self.ps_t = make_type(X.PS_CLASS, [
            make_prop('ExperienceState', 'ZArrayProperty', Inner=make_prop('ExperienceState', 'ZStructProperty', Struct=self.entry_t)),
        ])
        self.ps = Node(
            Class=self.ps_t, _type=self.ps_t,
            _path_name=lambda: '/Game/World.OakPlayerState_0',
            ExperienceState=[self.char_entry, self.spec_entry],
        )
        self.pc = Node(_path_name=lambda: '/Game/World.OakPlayerController_0')
        self.pawn = Node(_path_name=lambda: '/Game/World.OakCharacter_0')

        outer = Node(_path_name=lambda: '/Script/OakGame.OakExperienceStatics')
        self.award_fn = Node(
            Name='AwardKillExperienceToParty', Outer=outer, NumParams=2,
            _path_name=lambda: X.AWARD_KILL_PATH,
            _properties=lambda: [
                make_prop('ContextActor', 'ZObjectProperty'),
                make_prop('OptionalKiller', 'ZObjectProperty'),
            ],
        )

    def make_entry(self, name, lvl, pts, prev_r, next_r, unlocked=True):
        return Node(
            _type=self.entry_t,
            ExperienceLevel=lvl,
            ExperiencePoints=pts,
            ExperiencePointsRequiredForPreviousLevel=prev_r,
            ExperiencePointsRequiredForNextLevel=next_r,
            ExperienceId=Node(_type=self.sname_t, Name=name),
            bIsUnlocked=unlocked,
        )

    def context(self):
        return self.pc, self.pawn, self.ps, self.ok

    def test_typed_fsname_and_duplicate_track_rejected(self):
        snap = self.X.snapshot_experience(self.ps)
        self.assertEqual(snap['character']['level'], 32)
        self.assertEqual(snap['specialization']['level'], 14)

        # Plain string ExperienceId rejected (must be typed SName struct)
        self.char_entry.ExperienceId = 'oak2_characterxp_progression'
        with self.assertRaises(ValueError):
            self.X.snapshot_experience(self.ps)

        # Duplicate progression track rejected (never silently overwritten)
        self.char_entry.ExperienceId = Node(_type=self.sname_t, Name='oak2_characterxp_progression')
        self.ps.ExperienceState.append(self.make_entry('oak2_characterxp_progression', 1, 0, 0, 100))
        with self.assertRaises(ValueError):
            self.X.snapshot_experience(self.ps)

    def test_matched_pre_post_and_mismatched_or_stale_rejected(self):
        obs = self.X.KillExperienceObserver(self.context, lambda: self.time, lambda: self.tid)
        enemy1 = Node()
        enemy2 = Node()
        # Mismatched ContextActor in POST rejected
        obs.on_pre(None, Node(ContextActor=enemy1, OptionalKiller=self.pc))
        self.char_entry.ExperiencePoints += 450
        obs.on_post(None, Node(ContextActor=enemy2, OptionalKiller=self.pc))
        self.assertEqual(len(obs.events), 0)

        # Stale pending cleared by early return in PRE (foreign killer)
        obs.on_pre(None, Node(ContextActor=enemy1, OptionalKiller=self.pc))
        self.assertIsNotNone(obs.pending)
        obs.on_pre(None, Node(ContextActor=enemy1, OptionalKiller=Node()))
        self.assertIsNone(obs.pending)

        # Matched PRE/POST succeeds
        obs.on_pre(None, Node(ContextActor=enemy1, OptionalKiller=self.pc))
        self.char_entry.ExperiencePoints += 300
        self.spec_entry.ExperiencePoints += 300
        obs.on_post(None, Node(ContextActor=enemy1, OptionalKiller=self.pc))
        self.assertEqual(len(obs.events), 1)
        self.assertEqual(obs.events[0]['deltas']['character']['delta_points'], 300)
        self.assertEqual(obs.events[0]['deltas']['specialization']['delta_points'], 300)

    def test_inspect_globals_experience_combat_modifier(self):
        FGbxDefPtr = type('FGbxDefPtr', (), {})
        ptr = FGbxDefPtr()
        ptr._name = 'Att_PlayerDifficulty_CombatXP_Multiplier'
        g_t = make_type(self.X.GLOBALS_EXP, [make_prop('CombatExperienceModifier', 'ZGbxDefPtrProperty')])
        g_obj = Node(_type=g_t, CombatExperienceModifier=ptr)
        self.assertEqual(self.X.inspect_globals_experience(g_obj), 'Att_PlayerDifficulty_CombatXP_Multiplier')
        obs = self.X.KillExperienceObserver(self.context, lambda: self.time, lambda: self.tid)
        text = '\n'.join(obs.report_lines(globals_obj=g_obj))
        self.assertIn('OakGlobalsExperience.CombatExperienceModifier=Att_PlayerDifficulty_CombatXP_Multiplier', text)


if __name__ == '__main__':
    unittest.main()
