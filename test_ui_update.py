"""Focused UI/hook regression cases; mocks only, not native FPS or window tests."""
import types
import unittest
import test_batch
import test_foundation

class Update(unittest.TestCase):
    def setUp(self):
        self.b=test_batch.Batch(); self.b.setUp(); self.addCleanup(self.b.doCleanups)
        self.m=self.b.m; self.gui=self.b.gui; self.ui=self.gui.imgui
        self.ui.Key=types.SimpleNamespace(f8='f8',escape='esc',f9='f9')
        self.down=set(); self.pressed=set()
        self.ui.is_key_down=lambda k:k in self.down
        self.ui.is_key_pressed=lambda k,repeat=True:k in self.pressed
    def test_new_id_old_hook_not_touched(self):
        old=(self.m._MONITOR_PATH,'post','bl4_custom_legendary_session_guard_v051')
        self.b.hooks[old]=object(); original=self.b.hooks[old]
        self.assertTrue(self.m.ensure_monitor()); self.assertIs(self.b.hooks[old],original)
        self.assertEqual(len(self.b.hooks),2)
    def test_repeat_registration_no_new_hook(self):
        for _ in range(5): self.assertTrue(self.m.ensure_monitor())
        self.assertEqual(len(self.b.hooks),1)
    def test_duplicate_same_id_fail_closed(self):
        self.m._monitor_registered=False; self.m._monitor_candidate=False; self.m._monitor_attempted=False
        self.assertFalse(self.m.ensure_monitor()); self.b.activate('legendary_weight',2)
        self.assertEqual(self.b.f.writes,[]); self.assertIn('duplicate SDKMOD copies',self.b.report())
    def test_reentry_refused(self):
        self.m._monitor_registering=True
        self.assertFalse(self.m.ensure_monitor()); self.assertEqual(len(self.b.hooks),1)
    def test_open_no_diagnostics(self):
        self.m.close_menu(); self.gui.finish_close()
        self.m.inspect_attribute_compatibility=lambda:self.fail('automatic reflection')
        self.m.inspect_loot_readonly=lambda:self.fail('automatic report')
        self.m.open_key.callback(); self.m.draw(); self.assertTrue(self.gui.active)
    def test_idle_no_scan(self):
        self.m.close_menu(); self.gui.finish_close()
        self.m.conflicting_mods=lambda:self.fail('idle conflict scan')
        for _ in range(10): self.m.monitor_tick()
        self.assertFalse(self.b.path.exists())
    def test_active_guard_retained(self):
        self.b.activate('legendary_weight',2); self.m.close_menu(); self.gui.finish_close()
        self.b.f.players=2; self.m.monitor_tick(); self.assertEqual(self.b.f.weight,1.)
    def test_opening_press_ignored_then_f8_closes(self):
        self.down={'f8'}; self.pressed={'f8'}; self.m.draw(); self.assertEqual(self.gui.closes,0)
        self.down.clear(); self.pressed.clear(); self.m.draw()
        self.down={'f8'}; self.pressed={'f8'}; self.m.draw(); self.assertEqual(self.gui.closes,1)
    def test_escape(self):
        self.m.draw(); self.pressed={'esc'}; self.m.draw(); self.assertEqual(self.gui.closes,1)
    def test_rebound_fkey(self):
        self.m.open_key.key='F9'; self.m.draw(); self.pressed={'f9'}; self.m.draw(); self.assertEqual(self.gui.closes,1)
    def test_native_exit_flag_in_draw(self):
        self.gui.exit_requested=True; self.m.draw(); self.assertEqual(self.gui.closes,1); self.assertIsNone(self.m._backend)
    def test_native_exit_flag_in_monitor(self):
        self.gui.exit_requested=True; self.m.monitor_tick(); self.assertEqual(self.gui.closes,1); self.assertIsNone(self.m._backend)
    def test_external_teardown_clears_local_state(self):
        self.gui.finish_close(); self.m.monitor_tick(); self.assertIsNone(self.m._backend); self.assertEqual(self.gui.closes,0)
    def test_close_cancels_queued_action(self):
        self.m.activate_feature('legendary_weight',2); self.gui.exit_requested=True; self.m.monitor_tick(); self.assertEqual(self.b.f.writes,[])
    def test_foreign_window_not_closed(self):
        self.gui.title='Another mod'; self.gui.exit_requested=True; self.m.monitor_tick(); self.assertEqual(self.gui.closes,0); self.assertIsNone(self.m._backend)
    def test_ui_close_does_not_deactivate(self):
        self.b.activate('legendary_weight',2); self.m.draw(); self.pressed={'esc'}; self.m.draw(); self.m.monitor_tick(); self.assertEqual(self.b.f.weight,2.)
