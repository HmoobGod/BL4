"""Mock local animation lifecycle, no actual game speed or FPS evidence."""
import unittest
import types
import sys
import test_expansion

class Ground(unittest.TestCase):
    def setUp(self):
        self.e=test_expansion.Expansion();self.e.setUp();self.addCleanup(self.e.doCleanups)
        self.b=self.e.b;self.m=self.e.m;self.c=self.b.jump;self.anim=self.e.anim
        self.enemy=types.SimpleNamespace(_get_address=lambda:1234)
    def queue(self,x=2.): self.b.activate('walk_speed',x)
    def tick(self,obj=None): self.m.ground_tick(self.anim if obj is None else obj)
    def start(self,x=2.): self.queue(x);self.tick();self.assertIn('walk_speed',self.m._controller.records)
    def test_no_startup_hook(self): self.assertFalse(self.m._ground_inserted);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_only_player_animation(self):
        self.queue();self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick(self.enemy);self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_sprint_and_walk(self):
        self.start();self.c.bIsSprinting=True;self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1656.);self.c.bIsSprinting=False;self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_baseline_reset_reapplied_only_on_player_frame(self):
        self.start();self.c.MinAnalogWalkSpeed=0.;self.m.monitor_tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick(self.enemy);self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_foreign_drift_not_overwritten(self):
        self.start();self.c.MinAnalogWalkSpeed=777.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.c.MinAnalogWalkSpeed,777.)
    def test_restore_positive_original(self):
        self.c.MinAnalogWalkSpeed=120.;self.start();self.m.request_stop('test',immediate=True);self.assertEqual(self.c.MinAnalogWalkSpeed,120.);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,120.)
    def test_high_original_not_lowered(self):
        self.c.MinAnalogWalkSpeed=2000.;self.start();self.assertEqual(self.c.MinAnalogWalkSpeed,2000.);self.m.request_stop('test',immediate=True);self.assertEqual(self.c.MinAnalogWalkSpeed,2000.)
    def test_join_stops(self):
        self.start();self.b.f.players=2;self.c.bIsSprinting=True;self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1080.);self.m.monitor_tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_mismatched_character(self):
        self.b.f.pc.OakCharacter=self.enemy;self.queue();self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_stale_animation_restores(self):
        self.start();self.m._ground_seen=0.;self.m.monitor_tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_close_cancels_pending(self):
        self.queue();self.m.close_menu();self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_closed_active_keeps_speed(self):
        self.start();self.m.close_menu();self.b.gui.finish_close();self.c.bIsSprinting=True;self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1656.)
    def test_expiry(self):
        self.queue();k,v,t,_=self.m._activation_request;self.m._activation_request=(k,v,t,0);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_camera_hook_removed(self):
        self.queue();self.b.hooks.pop((self.m._MONITOR_PATH,'post',self.m._MONITOR_ID));self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_false_append_accepted_only_on_callback(self):
        def add(p,t,i,cb): self.b.hooks[p,t,i]=cb;return False
        self.b.f.sdk.hooks.add_hook=add;self.queue();self.assertEqual(self.c.MinAnalogWalkSpeed,0.);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_duplicate_not_adopted(self):
        k=(self.m._GROUND_PATH,'anim_post',self.m._GROUND_ID);self.b.hooks[k]=self.enemy;self.queue();self.tick();self.assertIs(self.b.hooks[k],self.enemy);self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_apex_conflict(self):
        old=sys.modules.get('apex_speed');sys.modules['apex_speed']=types.SimpleNamespace(mod=types.SimpleNamespace(is_enabled=True));self.addCleanup(self.b.restore_module,'apex_speed',old);self.queue();self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_wrong_owner(self):
        self.c.CharacterOwner=self.enemy;self.queue();self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_replaced_pawn_never_written(self):
        self.start();self.b.f.pc.Pawn=self.enemy;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.c.MinAnalogWalkSpeed,1080.)
    def test_unsupported_sprint(self):
        self.c.bIsSprinting=1;self.queue();self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_no_slow_speed(self):
        self.queue(.5);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
    def test_legacy_out_of_range_selection(self):
        self.queue(4.7);self.tick();self.assertEqual(self.c.MinAnalogWalkSpeed,0.)
