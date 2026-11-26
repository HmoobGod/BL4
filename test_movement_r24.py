"""Local dash and glide reflection and restoration, synthetic only."""
import unittest
from test_combat_r13 import Combat, Node, attr, typ, desc

class Movement(unittest.TestCase):
    def setUp(self):
        self.c=Combat(); self.c.setUp(); self.addCleanup(self.c.doCleanups)
        self.m=self.c.m; self.p=self.c.p
        self.dash=attr(1200.); self.glide=attr(800.)
        self.comp=Node(Class=typ('OakCharacterMovementComponent',desc('DashSpeed',self.dash._type),desc('GlidingSpeed',self.glide._type)),OakCharacterOwner=self.p,CharacterOwner=self.p,DashSpeed=self.dash,GlidingSpeed=self.glide)
        self.p.CharacterMovement=self.comp
    def test_independent(self):
        self.c.activate('dash_speed',1.5); self.c.activate('glide_speed',.5)
        self.assertEqual(self.c.vals(self.dash),(1800.,1800.)); self.assertEqual(self.c.vals(self.glide),(400.,400.))
        self.c.activate('dash_speed',1.); self.assertEqual(self.c.vals(self.dash),(1200.,1200.)); self.assertEqual(self.c.vals(self.glide),(400.,400.))
        self.c.activate('glide_speed',1.); self.assertEqual(self.c.vals(self.glide),(800.,800.))
    def test_update_relative(self):
        self.c.activate('dash_speed',2.); self.c.activate('dash_speed',3.); self.assertEqual(self.c.vals(self.dash),(3600.,3600.))
    def test_manual_default(self):
        for k in ('dash_speed','glide_speed'): self.assertNotIn(k,self.m.AUTO_OPTIONS)
        self.assertEqual(self.dash.writes+self.glide.writes,[])
    def test_wrong_owner(self):
        self.comp.OakCharacterOwner=Node(); self.c.activate('dash_speed',2.); self.assertEqual(self.dash.writes,[])
    def test_conflicting_owner(self):
        self.comp.PawnOwner=Node(); self.c.activate('glide_speed',2.); self.assertEqual(self.glide.writes,[])
    def test_default_component(self):
        self.comp.Name='Default__OakCharacterMovementComponent'; self.c.activate('dash_speed',2.); self.assertEqual(self.dash.writes,[])
    def test_wrong_class(self):
        self.comp.Class.Name='CharacterMovementComponent'; self.c.activate('dash_speed',2.); self.assertEqual(self.dash.writes,[])
    def test_missing_descriptor(self):
        self.comp.Class._properties=lambda:[]; self.c.activate('dash_speed',2.); self.assertEqual(self.dash.writes,[])
    def test_unequal_pair(self):
        self.dash._values['Value']=1400.; self.c.activate('dash_speed',2.); self.assertEqual(self.dash.writes,[])
    def test_join_restore(self):
        self.c.activate('dash_speed',2.); self.c.activate('glide_speed',2.); self.c.b.f.players=2; self.m.monitor_tick()
        self.assertEqual(self.c.vals(self.dash),(1200.,1200.)); self.assertEqual(self.c.vals(self.glide),(800.,800.))
    def test_foreign_drift(self):
        self.c.activate('dash_speed',2.); self.dash._values['Value']=2500.; self.m.monitor_tick(); self.assertTrue(self.m._controller.fault); self.assertEqual(self.dash.Value,2500.)
    def test_replacement(self):
        self.c.activate('dash_speed',2.); other=attr(1200.); self.comp.DashSpeed=other; self.comp.Class._properties=lambda:[desc('DashSpeed',other._type)]; self.m.monitor_tick(); self.assertTrue(self.m._controller.fault); self.assertEqual(other.writes,[])
