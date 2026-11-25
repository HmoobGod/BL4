"""R5 mock regressions: R2 admission parity, never a native privacy test."""
import unittest
from test_r3_persistent import Persistent

class R5(unittest.TestCase):
    def setUp(self):
        self.p=Persistent(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.m=self.p.m; self.f=self.p.f; self.f.solo=False
    def test_r2_eligible_host_ground_full_cycle(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.)
        self.m.queue_auto_edit(self.m._ground_selection,1.5)
        self.m.flush_auto_edits(force=True); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,810.)
        self.m.set_auto_setting(self.m.auto_master,False); self.p.tick()
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_r2_eligible_host_nonmovement_and_join_restore(self):
        self.p.configure(legendary_weight=3); self.p.tick()
        self.assertEqual(self.f.writes,[3.]); self.f.players=2; self.p.tick()
        self.assertEqual(self.f.writes,[3.,1.]); self.p.tick()
        self.assertEqual(self.f.writes,[3.,1.])
    def test_unknown_standalone_refused(self):
        self.f.solo=None; self.p.configure(legendary_weight=3); self.p.tick()
        self.assertEqual(self.f.writes,[])
    def test_host_without_consent_refused(self):
        self.p.configure(legendary_weight=3); self.m.apply({'persistent_offline':False}); self.p.tick()
        self.assertEqual(self.f.writes,[])
    def test_host_dedicated_refused(self):
        self.f.ded=True; self.p.configure(legendary_weight=3); self.p.tick()
        self.assertEqual(self.f.writes,[])
    def test_host_without_local_controller_refused(self):
        self.f.pc.IsLocalPlayerController=lambda:False
        self.p.configure(legendary_weight=3); self.p.tick(); self.assertEqual(self.f.writes,[])
    def test_host_without_authority_refused(self):
        self.f.pc.HasAuthority=lambda:False
        self.p.configure(legendary_weight=3); self.p.tick(); self.assertEqual(self.f.writes,[])
    def test_host_pending_ground_join_refused(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.assertIsNotNone(self.m._auto_ground)
        self.f.players=2; self.m.ground_tick(self.p.anim); self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_host_active_ground_join_restores(self):
        self.p.configure(walk_speed=2); self.p.tick(); self.m.ground_tick(self.p.anim)
        self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,1080.)
        self.f.players=2; self.p.tick(); self.assertEqual(self.p.b.jump.MinAnalogWalkSpeed,0.)
    def test_nonstandalone_client_refused(self):
        self.f.server=False; self.p.configure(legendary_weight=3); self.p.tick()
        self.assertEqual(self.f.writes,[])
