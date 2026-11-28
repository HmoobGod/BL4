"""Individual toggle UI contracts; mock SDK only, no gameplay claims."""
import unittest
from test_r3_persistent import Persistent

class SimpleF8(unittest.TestCase):
    def setUp(self):
        self.p=Persistent();self.p.setUp();self.addCleanup(self.p.doCleanups)
        self.m=self.p.m;self.f=self.p.f
        self.m.open_key.callback()
        self.m._category=2
        self.ui=self.p.b.gui.imgui
    def render(self, edits=None, clicks=()):
        self.ui.edits=edits or {};self.ui.clicks=set(clicks);self.ui.labels=[]
        self.m.draw();return self.ui.labels
    def consent(self):
        self.render({'I use Offline Local Only; tuning mods disabled##persistent_offline':True})
    def toggle(self,key,value):
        self.m.set_feature_enabled(self.m.AUTO_OPTIONS[key],value)
    def test_visible_controls(self):
        labels=self.render()
        self.assertIn('Enable Legendary rarity weight##persistent_legendary_weight',labels)
        self.assertEqual(labels.count('Restore All'),1)
        self.assertFalse(any('##persistent_master' in x or 'Activate / Update Legendary' in x for x in labels))
        self.assertNotIn('Apply and save',labels)
    def test_first_enable_and_live_slider(self):
        self.consent()
        self.render({'Legendary rarity weight (selected)##legendary_weight':3.,'Enable Legendary rarity weight##persistent_legendary_weight':True})
        self.assertEqual(self.f.writes,[])
        self.p.tick();self.assertEqual(self.f.writes,[3.])
        self.render({'Legendary rarity weight (selected)##legendary_weight':4.})
        self.p.tick();self.assertEqual(self.f.writes,[3.])
        self.m.flush_auto_edits(force=True);self.p.tick();self.assertEqual(self.f.writes,[3.,4.])
    def test_off_restores_only_selected(self):
        self.p.configure(legendary_weight=3,repair_cooldown=.1);self.p.tick();self.p.tick()
        self.toggle('legendary_weight',False);self.p.tick()
        self.assertEqual(self.f.weight,1.);self.assertEqual(self.p.b.cool.Value,2.)
        self.assertTrue(self.m.auto_master.value)
        self.toggle('repair_cooldown',False);self.p.tick()
        self.assertEqual(self.p.b.cool.Value,20.);self.assertFalse(self.m.auto_master.value)
    def test_legacy_off_no_rearm(self):
        self.m.apply({'persistent_master':False,'persistent_offline':True,'persistent_legendary_weight':True,'legendary_weight':3.,'repair_cooldown':.1})
        self.assertFalse(self.m.feature_enabled(self.m.AUTO_OPTIONS['legendary_weight']))
        self.toggle('repair_cooldown',True);self.p.tick()
        self.assertEqual(self.f.writes,[]);self.assertFalse(self.m.AUTO_OPTIONS['legendary_weight'].value)
        self.assertEqual(self.m._PREVIEW_BY_KEY['legendary_weight'].value,3.)
        self.assertEqual(self.p.b.cool.Value,2.)
    def test_restore_all_clears_flags_and_keeps_values(self):
        self.p.configure(legendary_weight=3,repair_cooldown=.1);self.p.tick();self.p.tick()
        self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY['legendary_weight'],4.)
        self.render(clicks=['Restore All']);self.p.tick()
        self.assertFalse(any(f.value for f in self.m.feature_flags()))
        self.assertFalse(self.m.auto_master.value);self.assertEqual(self.f.weight,1.)
        self.assertEqual(self.p.b.cool.Value,20.);self.assertEqual(self.m._PREVIEW_BY_KEY['legendary_weight'].value,4.)
        saved=self.m.mod.saved;self.m.mod.restore(saved);self.m.enabled();self.p.tick()
        self.assertEqual(self.f.writes,[3.,1.])
    def test_save_failure_on_disable_stops(self):
        self.p.configure(legendary_weight=3);self.p.tick();self.m.mod.fail_save=True
        self.toggle('legendary_weight',False);self.p.tick()
        self.assertFalse(self.m.auto_master.value);self.assertEqual(self.f.writes,[3.,1.])
    def test_restore_save_failure_disarms(self):
        self.p.configure(legendary_weight=3);self.p.tick();self.m.mod.fail_save=True
        self.m.restore_all_ui();self.p.tick()
        self.assertFalse(any(f.value for f in self.m.feature_flags()));self.assertEqual(self.f.weight,1.)
    def test_no_consent_no_game_write(self):
        self.m.apply({'legendary_weight':3.});self.toggle('legendary_weight',True);self.p.tick()
        self.assertEqual(self.f.writes,[])
    def test_automatic_restore_on_join(self):
        self.consent();self.m.apply({'legendary_weight':3.});self.toggle('legendary_weight',True);self.p.tick()
        self.f.players=2;self.p.tick();self.assertEqual(self.f.writes,[3.,1.])
    def test_manual_active_cannot_auto_enable(self):
        self.p.b.activate('jump',2.)
        self.toggle('legendary_weight',True);self.assertFalse(self.m.auto_master.value)
    def test_automation_toggle_first_enable_reachable(self):
        self.m._category=5;labels=self.render()
        flag=self.m.AUTOMATION_OPTIONS['reload'];self.assertIn(flag.display_name+'##'+flag.identifier,labels)
        self.assertNotIn('Automatic reload##auto_reload',labels)
        self.m.set_feature_enabled(flag,True);self.assertTrue(self.m.auto_master.value);self.assertTrue(flag.value)
        self.m.set_feature_enabled(flag,False);self.assertFalse(self.m.auto_master.value)
    def test_failed_xp_not_offered(self):
        self.m._category=1;labels=self.render()
        self.assertFalse(any('Test earned Enemy kill XP' in x for x in labels))
        self.assertTrue(any('Test earned Money' in x for x in labels))
    def test_consent_withdrawal_save_failure_disarms(self):
        self.p.configure(legendary_weight=3);self.p.tick();self.m.mod.fail_save=True
        self.render({'I use Offline Local Only; tuning mods disabled##persistent_offline':False});self.p.tick()
        self.assertFalse(self.m.auto_consent.value);self.assertEqual(self.f.weight,1.)

    def test_vacuum_preferences_auto_save(self):
        self.m._category=5;self.render({'Vacuum cash##vacuum_cash':True,'Pickup radius##vacuum_radius':45.})
        self.m.flush_auto_edits(force=True)
        self.assertTrue(self.m.VACUUM_PREFS['cash'].value);self.assertEqual(self.m.VACUUM_RADIUS_PREF.value,45.)
        self.assertFalse(self.m.auto_master.value);self.assertFalse(self.m.health_active())
    def test_legacy_on_with_no_flags_is_idle(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True});self.m.enabled()
        self.assertFalse(self.m.auto_master.value);self.p.tick();self.assertEqual(self.f.writes,[])

    def test_failed_xp_queue_rejected(self):
        self.consent(); self.m.activate_feature('progress_enemy_xp',2.)
        self.assertIsNone(self.m._activation_request)
        self.assertIn('XP experiment failed',self.m._loot_test_status)

    def test_failed_xp_dispatch_rejected(self):
        seen=[];self.m.begin_blackboard_reward=lambda *args:seen.append(args)
        with self.assertRaisesRegex(ValueError,'XP experiment failed'):
            self.m.execute_activation('progress_enemy_xp',2.)
        self.assertEqual(seen,[])

    def test_failed_xp_begin_rejected_before_sdk_discovery(self):
        import sys
        from unittest.mock import patch
        with patch.dict(sys.modules,{'unrealsdk':None}):
            with self.assertRaisesRegex(ValueError,'XP experiment failed'):
                self.m.begin_blackboard_reward('progress_enemy_xp',2.)
        self.assertFalse(self.m.health_active())

    def test_blocked_xp_does_not_stop_other_feature(self):
        self.p.b.activate('jump',2.)
        self.assertIn('jump',self.m._controller.records)
        self.m.activate_feature('progress_enemy_xp',2.)
        self.assertIsNone(self.m._controller.stop_pending)
        self.assertIn('jump',self.m._controller.records)

    def test_cash_and_eridium_dispatch_preserved(self):
        seen=[];self.m.begin_blackboard_reward=lambda *args:seen.append(args)
        for key in ('progress_money','progress_eridium'):
            self.m.execute_activation(key,2.)
        self.assertEqual(seen,[('progress_money',2.),('progress_eridium',2.)])
