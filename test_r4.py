"""R4 focused mocks: no native performance or gameplay claims."""
import unittest
import types
from test_r3_persistent import Persistent

class R4(unittest.TestCase):
    def setUp(self):
        self.p=Persistent(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.m=self.p.m; self.f=self.p.f
    def test_new_feature_waits_for_edit_commit(self):
        self.p.configure(legendary_weight=3)
        opt=next(o for o in self.m.PREVIEW if o.identifier=='legendary_weight')
        self.m.queue_auto_edit(opt,5); self.p.tick()
        self.assertEqual(self.f.writes,[])
        self.m.flush_auto_edits(force=True); self.p.tick()
        self.assertEqual(self.f.writes,[5.])
    def test_queued_ground_never_applies_stale_slider(self):
        self.p.configure(walk_speed=2); self.p.tick()
        self.assertIsNotNone(self.m._auto_ground)
        self.m.queue_auto_edit(self.m._ground_selection,1.5)
        self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
        self.p.tick(); self.assertIsNone(self.m._auto_ground)
        self.m.flush_auto_edits(force=True); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,810.)
    def test_master_off_preserves_uncommitted_slider(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.m.queue_auto_edit(self.m._ground_selection,1.5)
        self.m.set_auto_setting(self.m.auto_master,False); self.p.tick()
        self.assertEqual(self.m._ground_selection.value,1.5)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
        self.assertFalse(self.m.auto_master.value)
    def test_failed_master_save_still_disarms(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.m.queue_auto_edit(self.m._ground_selection,1.5)
        self.m.mod.fail_save=True; self.m.set_auto_setting(self.m.auto_master,False); self.p.tick()
        self.assertFalse(self.m.auto_master.value); self.assertFalse(self.m._auto_edits)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_compact_persistent_hides_held_controls(self):
        self.p.configure(damage_taken=.5); self.m.open_key.callback(); self.m._category=0
        ui=self.p.b.gui.imgui; ui.labels=[]; self.m.draw(); compact_count=len(ui.labels)
        self.assertNotIn('Damage multiplier##damage',ui.labels)
        self.assertIn('Damage taken multiplier##damage_taken',ui.labels)
        self.assertIn('Auto-enable Damage taken multiplier##persistent_damage_taken',ui.labels)
        ui.edits={'Compact menu (hide preview-only controls)':False}; ui.labels=[]; self.m.draw()
        self.assertIn('Damage multiplier##damage',ui.labels); self.assertGreater(len(ui.labels),compact_count)
    def test_status_does_not_query_sdk(self):
        self.p.configure(legendary_weight=3); self.p.tick()
        self.m._controller.context=lambda:self.fail('UI must not query game')
        self.assertEqual(self.m.persistent_feature_status('legendary_weight'),'Active: 3x (value verified)')
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['legendary_weight'],False)
        self.assertEqual(self.m.persistent_feature_status('legendary_weight'),'Off (restoring)')
    def test_alias_path_and_owner_checks_once(self):
        from bl4_custom_foundation.gameplay_fields import read_fields
        self.f.pawn.CharMoveComp=self.p.b.jump; self.f.pawn.MovementComponent=self.p.b.jump
        original=self.p.b.jump._path_name; calls=[]
        self.p.b.jump._path_name=lambda:(calls.append(True),original())[1]
        _,_,values=read_fields('walk_speed',self.f.pawn,self.f.state)
        self.assertEqual(values,(0.,)); self.assertEqual(len(calls),1)
    def test_idle_preflight_throttled(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.m._auto_next=float('inf')
        calls=[]
        self.m.conflicting_mods=lambda:(calls.append(True),False)[1]
        self.m.monitor_tick()
        self.assertEqual(calls,[])
    def test_active_guard_not_throttled(self):
        self.p.configure(legendary_weight=3); self.p.tick(); self.m._auto_next=float('inf')
        self.f.players=2; self.m.monitor_tick(); self.assertEqual(self.f.writes,[3.,1.])
    def test_pending_ground_guard_not_throttled(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.m._auto_next=float('inf')
        self.m.apply({'persistent_offline':False}); self.m.monitor_tick(); self.assertIsNone(self.m._auto_ground)
        self.m.ground_tick(self.p.anim); self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
