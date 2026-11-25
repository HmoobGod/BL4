"""R3 mock tests: persistent settings, callback admission, restoration and operation counts.
No native SDK/game execution, timing or FPS measurement."""
import unittest
import types
import sys
import test_expansion

class Persistent(unittest.TestCase):
    def setUp(self):
        self.e=test_expansion.Expansion(); self.e.setUp(); self.addCleanup(self.e.doCleanups)
        self.b=self.e.b; self.m=self.e.m; self.f=self.b.f; self.anim=self.e.anim
        self.f.solo=True
        self.m.close_menu(); self.b.gui.finish_close()
    def configure(self, **values):
        self.m.apply({**values, 'persistent_master':True,'persistent_offline':True,
                      **{'persistent_'+k:True for k in values}})
    def tick(self):
        self.m._auto_next=0.; self.m.monitor_tick()
    def test_defaults_no_migration(self):
        self.m.apply({'legendary_weight':5,'walk_speed':2}); self.tick()
        self.assertEqual(self.f.writes,[]); self.assertIsNone(self.m._controller)
    def test_only_explicit_feature_enabled(self):
        self.configure(legendary_weight=3); self.m.apply({'repair_cooldown':.1}); self.tick()
        self.assertEqual(self.f.writes,[3.]); self.assertEqual(self.b.cool.writes,[])
    def test_saved_settings_relaunch(self):
        self.configure(legendary_weight=3); saved=self.m.mod.saved
        self.m.apply({'persistent_master':False,'persistent_offline':False,'legendary_weight':1,'persistent_legendary_weight':False})
        self.m.mod.restore(saved); self.m.enabled(); self.tick()
        self.assertEqual(self.f.writes,[3.])
    def test_no_consent(self):
        self.configure(legendary_weight=3); self.m.apply({'persistent_offline':False}); self.tick()
        self.assertEqual(self.f.writes,[])
    def test_nonstandalone_single_host_with_consent_admitted(self):
        self.f.solo=False; self.configure(legendary_weight=3); self.tick(); self.assertEqual(self.f.writes,[3.])
    def test_multiplayer_refused_even_standalone_flag(self):
        self.f.players=2; self.configure(legendary_weight=3); self.tick(); self.assertEqual(self.f.writes,[])
    def test_client_refused(self):
        self.f.server=False; self.configure(legendary_weight=3); self.tick(); self.assertEqual(self.f.writes,[])
    def test_master_off_restores(self):
        self.configure(legendary_weight=3); self.tick(); self.m.set_auto_setting(self.m.auto_master,False); self.tick()
        self.assertEqual(self.f.writes,[3.,1.]); self.tick(); self.assertEqual(self.f.writes,[3.,1.])
    def test_feature_off_restores_only_it(self):
        self.configure(legendary_weight=3,repair_cooldown=.1); self.tick(); self.tick()
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['legendary_weight'],False); self.tick()
        self.assertEqual(self.f.weight,1.); self.assertEqual(self.b.cool.Value,2.)
    def test_1x_restores(self):
        self.configure(legendary_weight=3); self.tick(); self.m.apply({'legendary_weight':1}); self.tick(); self.assertEqual(self.f.weight,1.)
    def test_consent_off_restores(self):
        self.configure(legendary_weight=3); self.tick(); self.m.set_auto_setting(self.m.auto_consent,False); self.tick(); self.assertEqual(self.f.weight,1.)
    def test_join_restores_and_clean_return_reapplies(self):
        self.configure(legendary_weight=3); self.tick(); self.f.players=2; self.f.solo=False; self.tick()
        self.assertEqual(self.f.writes,[3.,1.]); self.tick(); self.f.players=1; self.f.solo=True; self.tick()
        self.assertEqual(self.f.writes,[3.,1.,3.])
    def test_drift_does_not_reapply(self):
        self.configure(legendary_weight=3); self.tick(); self.f.weight=1.; self.tick(); self.tick()
        self.assertEqual(self.f.writes,[3.]); self.assertIn('Unexpected',self.m._auto_blocked)
    def test_foreign_drift_fault(self):
        self.configure(legendary_weight=3); self.tick(); self.f.weight=7.; self.tick(); self.tick()
        self.assertTrue(self.m._controller.fault); self.assertEqual(self.f.weight,7.)
    def test_failed_activation_not_retried(self):
        self.f.weight=.5; self.configure(legendary_weight=3); self.tick(); self.tick()
        self.assertEqual(self.f.writes,[]); self.assertIn('Activation failed',self.m._auto_blocked)
    def test_conflict_restoration(self):
        self.configure(legendary_weight=3); self.tick(); old=sys.modules.get('LootTreadmill')
        sys.modules['LootTreadmill']=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=True))
        self.addCleanup(self.b.restore_module,'LootTreadmill',old); self.tick(); self.assertEqual(self.f.weight,1.)
    def test_monitor_missing_no_write(self):
        self.configure(legendary_weight=3); self.b.hooks.clear(); self.tick(); self.assertEqual(self.f.writes,[])
    def test_restore_all_pauses(self):
        self.configure(legendary_weight=3); self.tick(); self.m.pause_auto('F8 restore all'); self.m.request_stop('F8 restore all'); self.tick(); self.tick()
        self.assertFalse(self.m.auto_master.value); self.assertEqual(self.f.writes,[3.,1.])
    def test_no_reapply_after_stop(self):
        self.configure(legendary_weight=3); self.tick(); self.m.request_stop('test'); self.tick(); self.tick(); self.assertEqual(self.f.writes,[3.,1.])
    def test_save_failure_stops_auto(self):
        self.configure(legendary_weight=3); self.tick(); self.m.mod.fail_save=True; self.m.set_auto_setting(self.m.auto_master,False); self.tick(); self.tick()
        self.assertEqual(self.f.writes,[3.,1.]); self.assertIn('save failed', self.m._auto_blocked)
    def test_live_edit_debounce(self):
        self.configure(legendary_weight=3); self.tick(); option=next(o for o in self.m.PREVIEW if o.identifier=='legendary_weight')
        old=self.m.mod.save_count; self.m.queue_auto_edit(option,4); self.m.queue_auto_edit(option,5); self.m.flush_auto_edits(); self.tick()
        self.assertEqual(self.f.weight,3.); self.assertEqual(self.m.mod.save_count,old)
        self.m.flush_auto_edits(force=True); self.tick(); self.assertEqual(self.f.writes,[3.,5.]); self.assertEqual(self.m.mod.save_count,old+1)
    def test_ground_uses_local_animation_without_window(self):
        self.configure(walk_speed=2); self.tick(); self.assertIsNotNone(self.m._auto_ground)
        self.m.ground_tick(types.SimpleNamespace(_get_address=lambda:1234)); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
        self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1080.)
        self.b.jump.bIsSprinting=True; self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1656.)
        self.m.set_auto_setting(self.m.auto_master,False); self.tick(); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
    def test_ground_pending_feature_disabled_no_write(self):
        self.configure(walk_speed=2); self.tick(); self.m.set_auto_setting(self.m.AUTO_OPTIONS['walk_speed'],False); self.m.ground_tick(self.anim)
        self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
    def test_ground_pending_stale_setting_no_write(self):
        self.configure(walk_speed=2); self.tick(); self.m.apply({'walk_speed':3}); self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
        self.tick(); self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,1620.)
    def test_ground_pending_join_no_write(self):
        self.configure(walk_speed=2); self.tick(); self.f.solo=False; self.f.players=2; self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
    def test_ground_foreign_no_reapply(self):
        self.configure(walk_speed=2); self.tick(); self.m.ground_tick(self.anim); self.b.jump.MinAnalogWalkSpeed=777.; self.m.ground_tick(self.anim); self.tick()
        self.assertTrue(self.m._controller.fault); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,777.)
    def test_held_features_not_in_persistent_options(self):
        self.assertFalse(set(self.m.DAMAGE_HOLD)&set(self.m.AUTO_OPTIONS))
    def test_readonly_monitor_one_context_for_two_fields(self):
        self.configure(legendary_weight=3,repair_cooldown=.1); self.tick(); self.tick()
        c=self.m._controller; original=c.context; calls=[]
        def context(): calls.append(True); return original()
        c.context=context; self.tick(); self.assertEqual(len(calls),1)
    def test_steady_ground_frame_one_context_and_no_report(self):
        self.configure(walk_speed=2); self.tick(); self.m.ground_tick(self.anim)
        c=self.m._controller; original=c.context; calls=[]; reports=[]
        def context(): calls.append(True); return original()
        c.context=context; old=c.report; c.report=lambda x: (reports.append(x),old(x))[1]
        self.m.ground_tick(self.anim); self.assertEqual(len(calls),1); self.assertEqual(reports,[])

    def test_alias_reflection_once_preserves_distinct_owner_checks(self):
        from bl4_custom_foundation.gameplay_fields import read_fields
        self.f.pawn.CharMoveComp=self.b.jump
        self.f.pawn.MovementComponent=self.b.jump
        original=self.b.jump.Class._properties; calls=[]
        def props(): calls.append(True); return original()
        self.b.jump.Class._properties=props
        _, tokens, values=read_fields('walk_speed',self.f.pawn,self.f.state)
        self.assertEqual(len(calls),1); self.assertEqual(values,(0.,))
        import copy
        other=copy.copy(self.b.jump); other._get_address=lambda:12345
        self.f.pawn.MovementComponent=other
        with self.assertRaisesRegex(ValueError,'unique owned scalar'):
            read_fields('walk_speed',self.f.pawn,self.f.state)
    def test_wrong_context_pending_ground_no_write(self):
        self.configure(walk_speed=2); self.tick()
        self.f.state._get_address=lambda:123456789
        self.m.ground_tick(self.anim); self.assertEqual(self.b.jump.MinAnalogWalkSpeed,0.)
    def test_ui_saved_master_feature_toggles(self):
        self.m.open_key.callback(); self.m._category=2
        self.b.gui.imgui.edits={'I use Offline Local Only; tuning mods disabled##persistent_offline':True,'Persistent gameplay (experimental)##persistent_master':True}
        self.m.draw(); self.b.gui.imgui.edits={'Auto-enable Legendary rarity weight##persistent_legendary_weight':True,'Legendary rarity weight (selected)##legendary_weight':3.}
        self.m.draw(); self.assertEqual(self.f.writes,[]); self.m.close_menu(); self.tick()
        self.assertEqual(self.f.writes,[3.])

    def test_idle_master_no_feature_does_not_bind(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True})
        self.m.bound_session=lambda *a: self.fail('idle global reflection')
        self.tick(); self.assertIsNone(self.m._controller)
    def test_queued_manual_never_crosses_into_auto(self):
        self.m.open_key.callback(); self.m.activate_feature('legendary_weight',3.)
        self.assertIsNotNone(self.m._activation_request)
        self.m.apply({'persistent_master':True,'persistent_offline':True})
        self.tick(); self.assertIsNone(self.m._activation_request); self.assertEqual(self.f.writes,[])
