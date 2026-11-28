"""Synthetic shield-only native regeneration, not actual native timing evidence."""
from types import SimpleNamespace as N
from test_native_regen_r62 import NativeRegenTest
from test_combat_r13 import attr, Node


class NativeShieldRegen(NativeRegenTest):
    def setUp(self):
        super().setUp()
        self.shield.SimpleCurrentHealth=attr(50.)
        self.shield.SimpleMaxHealth=attr(100.)
        self.shield.SimpleCurrentHealth._type=self.cur._type
        self.shield.SimpleMaxHealth._type=self.max._type
        self.shield_pct=.5
        self.set_bound(self.funcs[0],self.shield_layer)
        self.set_bound(self.funcs[1],self.shield_percent)
    def shield_layer(self,p,h,top):
        self.assertIs(p,self.p);self.assertIs(top,False)
        if h is self.sh:return 0
        if h is self.hp:return 1
        raise ValueError('unexpected layer')
    def shield_percent(self,p,idx):
        self.assertIs(p,self.p)
        if idx==0:return self.shield_pct
        if idx==1:return self.pct
        raise ValueError('unexpected layer')
    def sample(self,p,dt=1.):
        self.shield_pct=p;self.shield.SimpleCurrentHealth._values['Value']=p*100
        self.advance(dt)
    def start(self):
        self.m.activate_feature('shield_regen_native',1.);self.m.monitor_tick()
    def rising(self):
        self.sample(.51);self.assertFalse(self.native)
        self.sample(.52);self.assertEqual(len(self.native),1)
    def test_shield_only_start_stop(self):
        self.start();self.assertTrue(self.m.health_active());self.rising()
        p,d,r,full,t,tags=self.native[0]
        self.assertIs(p,self.p);self.assertIs(tags,self.sh.GameplayTags)
        self.assertEqual((d,full,t,r.constant,r.PostScale),(2.,True,.5,.01,1.))
        self.sample(.53);self.assertEqual(self.stop_calls,[(self.p,71)])
        self.assertEqual(self.cur.Value,50.);self.assertFalse(self.calls)
        self.assertFalse(self.m.health_fault());self.start();self.assertFalse(self.m.health_active())
    def test_flat_stops(self):
        self.start();self.sample(.5);self.sample(.51);self.assertFalse(self.native);self.assertFalse(self.m.health_active())
    def test_fall_stops(self):
        self.start();self.sample(.51);self.sample(.50);self.assertFalse(self.native)
    def test_fast_stops(self):
        self.start();self.sample(.55);self.assertFalse(self.native)
    def test_stale_sample_stops(self):
        self.start();self.sample(.51,1.5);self.assertFalse(self.native)
    def test_armor_excluded(self):
        self.sh.DisplayColor=N(name='ArmorYellow');self.start();self.assertFalse(self.m.health_active())
    def test_overshield_excluded(self):
        self.sh.Variation=N(name='IsOvershield');self.start();self.assertFalse(self.m.health_active())
    def test_near_full_excluded(self):
        self.sample(.81,0.);self.start();self.assertFalse(self.m.health_active())
    def test_flesh_peer_drift_before_start(self):
        self.start();self.sample(.51);self.cur._values['Value']=49.;self.sample(.52);self.assertFalse(self.native)
    def test_flesh_peer_drift_after_start(self):
        self.start();self.rising();self.cur._values['Value']=51.;self.sample(.53,.1)
        self.assertEqual(self.stop_calls,[(self.p,71)]);self.assertTrue(self.m.health_fault())
    def test_overlapping_tag(self):
        self.hp.GameplayTags=self.tagset('Health.Shield.Child');self.start();self.assertFalse(self.m.health_active())
    def test_consent_loss_before_start(self):
        self.start();self.sample(.51);self.m._offline_confirmed=False;self.sample(.52);self.assertFalse(self.native)
    def test_shared_attempt_limit(self):
        self.m._native_overtime_used=True;self.start();self.sample(.51);self.sample(.52);self.assertFalse(self.native)
    def test_f8_shield_button(self):
        self.m._category=6;self.b.gui.imgui.clicks={'Test native shield regeneration (2 sec)'};self.m.draw()
        self.assertFalse(self.native);self.m.monitor_tick();self.assertTrue(self.m.health_active());self.rising()
    def test_shield_identity_change(self):
        self.start();self.sample(.51);self.sh._name='HealthType_Replacement';self.sample(.52);self.assertFalse(self.native)
    def test_stop_on_shield_full(self):
        self.start();self.rising();self.sample(1.,.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_stop_deferred_on_request(self):
        self.start();self.rising();self.m.request_stop('restore');self.assertFalse(self.stop_calls);self.sample(.53,.1);self.assertEqual(self.stop_calls,[(self.p,71)])
    def test_reentrant_stop_before_dispatch(self):
        self.start();self.sample(.51);lease=self.m._health_pulse;old=lease.context
        def ctx():
            result=old();self.m.request_stop('cancel before dispatch');return result
        lease.context=ctx;self.sample(.52);self.assertFalse(self.native)
    def test_peer_native_readback_alias(self):
        self.set_bound(self.funcs[0],lambda p,h,t:0)
        self.start();self.assertFalse(self.m.health_active());self.assertFalse(self.native)
    def test_peer_native_ratio_mismatch(self):
        self.pct=.4;self.start();self.assertFalse(self.m.health_active())
