"""R10 local gravity, synthetic SDK objects only."""
import unittest
import types
import test_r3_persistent
from struct import pack, unpack

class GravityControls(unittest.TestCase):
    def setUp(self):
        self.p=test_r3_persistent.Persistent(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.m,self.f,self.g=self.p.m,self.p.f,self.p.b.jump
    def test_default_off(self):
        self.assertFalse(self.m.AUTO_OPTIONS['gravity'].value)
        self.m.apply({'gravity':.5,'persistent_master':True,'persistent_offline':True}); self.p.tick()
        self.assertEqual(self.g.GravityScale,1.)
    def test_live_restore(self):
        self.p.configure(gravity=.5); self.p.tick(); self.assertEqual(self.g.GravityScale,.5)
        self.m.apply({'gravity':1.3}); self.p.tick(); self.assertEqual(self.g.GravityScale,unpack('<f',pack('<f',1.3))[0])
        self.m.apply({'gravity':1.}); self.p.tick(); self.assertEqual(self.g.GravityScale,1.)
        self.assertFalse(self.m._controller.records)
    def test_relative_nonunit_baseline(self):
        self.g.GravityScale=1.5; self.p.configure(gravity=.5); self.p.tick(); self.assertEqual(self.g.GravityScale,.75)
        self.m.apply({'gravity':1.});self.p.tick();self.assertEqual(self.g.GravityScale,1.5)
    def test_other_movement_fields_untouched(self):
        self.p.configure(gravity=.5);self.p.tick();self.assertEqual((self.g.JumpZVelocity,self.g.MaxWalkSpeed,self.g.MinAnalogWalkSpeed),(620.,600.,0.))
    def test_existing_ground_coexists(self):
        self.p.configure(gravity=.5,walk_speed=2.);self.p.tick();self.p.tick();self.m.ground_tick(self.p.anim)
        self.assertEqual((self.g.GravityScale,self.g.MinAnalogWalkSpeed),(.5,1080.))
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['gravity'],False);self.p.tick();self.assertEqual((self.g.GravityScale,self.g.MinAnalogWalkSpeed),(1.,1080.))
    def test_no_consent(self):
        self.p.configure(gravity=.5);self.m.apply({'persistent_offline':False});self.p.tick();self.assertEqual(self.g.GravityScale,1.)
    def test_join_restoration(self):
        self.p.configure(gravity=.5);self.p.tick();self.f.players=2;self.p.tick();self.assertEqual(self.g.GravityScale,1.)
    def test_master_off_restoration(self):
        self.p.configure(gravity=.5);self.p.tick();self.m.set_auto_setting(self.m.auto_master,False);self.p.tick();self.assertEqual(self.g.GravityScale,1.)
    def test_missing_field(self):
        del self.g.GravityScale;self.p.configure(gravity=.5);self.p.tick();self.assertIn('Activation failed',self.m._auto_blocked)
    def test_wrong_owner(self):
        self.g.CharacterOwner=types.SimpleNamespace(_get_address=lambda:12345);self.p.configure(gravity=.5);self.p.tick();self.assertEqual(self.g.GravityScale,1.)
    def test_foreign_drift(self):
        self.p.configure(gravity=.5);self.p.tick();self.g.GravityScale=1.25;self.p.tick();self.assertEqual(self.g.GravityScale,1.25);self.assertTrue(self.m._controller.fault)
    def test_other_component_refused(self):
        self.f.pawn.CharMoveComp=self.g
        self.f.pawn.CharacterMovement=types.SimpleNamespace(_get_address=lambda:12345)
        self.p.configure(gravity=.5);self.p.tick();self.assertEqual(self.g.GravityScale,1.)
    def test_bounds(self):
        from bl4_custom_foundation.gameplay_fields import target_values
        for v in (0.,.4,1.6,float('nan')):
            with self.assertRaises(ValueError):target_values('gravity',(1.,),((1,'GravityScale','ZFloatProperty'),),v)
