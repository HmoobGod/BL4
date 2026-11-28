"""Native shield pool backend, shared options and lifecycle (synthetic)."""
import unittest
from types import SimpleNamespace as N
from test_native_resource_rates import NativeRateTests

class PersistentShieldPoolTests(unittest.TestCase):
    def setUp(self):
        self.n=NativeRateTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
        self.m=self.n.base.m;self.R=self.n.R
    def setup_backend(self,mode='shield_idle_rate',scale=2.):
        m=self.m;k='native_rate_'+mode;key=m.SHIELD_POOL_KEYS[mode]
        m.auto_master.value=True;m.auto_consent.value=True
        m.SHIELD_POOL_BACKEND.value=True;m.AUTO_OPTIONS[key].value=True;m._PREVIEW_BY_KEY[key].value=scale
        return k,key
    def arm(self,mode='shield_idle_rate',scale=2.):
        n,m=self.n,self.m;k,key=self.setup_backend(mode,scale)
        prev=n.shield_pool_trial(mode,base=10.,selection=scale)
        lane=self.R.NativeRateTrial(mode,n.binding,n.resolve,prev.weak,prev.clock,prev.thread,n.msg.append,lambda:n.allowed and m.native_rate_allowed(k,lane.selection),prev.cleanup_key,selection=scale,continuous=True)
        m.automation_permitted=lambda:n.allowed
        self.assertTrue(lane.begin(),n.msg);n.tick(lane);self.assertEqual(lane.phase,'active',n.msg)
        m._automation_leases[k]=lane;m._automation_attempted.add(k)
        return k,key,lane
    def tick(self,dt=.3):self.n.now+=dt;self.m.automation_tick()
    def test_defaults_and_no_duplicate_settings(self):
        m=self.m;self.assertFalse(m.SHIELD_POOL_BACKEND.value)
        for mode,key in m.SHIELD_POOL_KEYS.items():
            k='native_rate_'+mode;o=m.NATIVE_RATE_OPTIONS[mode];f=m.NATIVE_AUTO_OPTIONS[k]
            self.assertIs(o,m._PREVIEW_BY_KEY[key]);self.assertIs(f,m.AUTO_OPTIONS[key])
            self.assertEqual(sum(x is o for x in m.ALL),1);self.assertEqual(sum(x is f for x in m.ALL),1);self.assertEqual(sum(x is f for x in m.feature_flags()),1)
            self.assertFalse(f.value);self.assertFalse(m.native_rate_allowed(k,2.))
    def test_legacy_default_routes_only_equipped_fields(self):
        m=self.m;k,key=self.setup_backend();m.SHIELD_POOL_BACKEND.value=False
        self.assertEqual(m.auto_desired(),{key:2.});self.assertFalse(m.native_rate_allowed(k,2.))
    def test_both_native_lanes_independent_and_no_legacy(self):
        m=self.m
        for mode in m.SHIELD_POOL_KEYS:self.setup_backend(mode)
        self.assertEqual(m.auto_desired(),{})
        for mode in m.SHIELD_POOL_KEYS:self.assertTrue(m.native_rate_allowed('native_rate_'+mode,2.))
        self.assertIn('shield modifier',m.recovery_conflict('shield'))
    def test_persistent_rate_and_depletion_then_off(self):
        k,key,l=self.arm();self.tick(40.);self.assertEqual(self.n.rate,20.);self.assertEqual(l.phase,'active');self.n.set_shield_charge(0.);self.tick()
        self.assertEqual(l.phase,'active');self.m.AUTO_OPTIONS[key].value=False;self.tick();self.tick()
        self.assertEqual(l.phase,'done');self.assertEqual(self.n.rate,10.);self.assertNotIn(k,self.m._automation_leases)
    def test_delay_edit_inverse_after_restoration(self):
        k,key,l=self.arm('shield_idle_delay',.5);self.assertEqual(self.n.rate,20.)
        self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY[key],2.);self.m.flush_auto_edits(force=True);self.assertEqual(l.next_selection,2.)
        self.tick();self.assertEqual(l.phase,'verify');self.assertEqual(self.n.rate,10.)
        self.tick();self.assertEqual(l.phase,'armed');self.tick();self.assertEqual(l.phase,'active');self.assertEqual(self.n.rate,5.)
        self.assertEqual([x[0] for x in self.n.native],['add','remove','add'])
    def test_neutral_restores(self):
        k,key,l=self.arm();self.m.apply({key:1.});self.tick();self.tick();self.assertNotIn(k,self.m._automation_leases);self.assertEqual(self.n.rate,10.)
    def test_backend_switch_refused_while_enabled_and_restoring(self):
        k,key,l=self.arm();m=self.m;m.set_auto_setting(m.SHIELD_POOL_BACKEND,False);self.assertTrue(m.SHIELD_POOL_BACKEND.value)
        m.AUTO_OPTIONS[key].value=False;self.tick();m.set_auto_setting(m.SHIELD_POOL_BACKEND,False);self.assertTrue(m.SHIELD_POOL_BACKEND.value)
        self.tick();m.set_auto_setting(m.SHIELD_POOL_BACKEND,False);self.assertFalse(m.SHIELD_POOL_BACKEND.value)
    def test_external_backend_change_drains_before_legacy_admission(self):
        k,key,l=self.arm();m=self.m;m.apply({m.SHIELD_POOL_BACKEND.identifier:False});self.assertNotIn(key,m.auto_desired());self.tick();self.assertNotIn(key,m.auto_desired());self.tick();self.assertEqual(m.auto_desired(),{key:2.});self.assertEqual(self.n.rate,10.)
    def test_legacy_active_blocks_native(self):
        k,key=self.setup_backend();self.m._controller=N(records={key:{}});self.assertFalse(self.m.native_rate_allowed(k,2.));self.m._controller=None
    def test_passive_and_refill_conflicts(self):
        m=self.m;k,key=self.setup_backend();m.NATIVE_AUTO_OPTIONS['native_rate_shieldpassive'].value=True;m.NATIVE_RATE_OPTIONS['shieldpassive'].value=2.
        self.assertFalse(m.native_rate_allowed(k,2.));self.assertFalse(m.native_rate_allowed('native_rate_shieldpassive',2.))
        m.NATIVE_AUTO_OPTIONS['native_rate_shieldpassive'].value=False;m.AUTOMATION_OPTIONS['shield'].value=True;self.assertFalse(m.native_rate_allowed(k,2.))
    def test_permission_loss_during_edit(self):
        k,key,l=self.arm();self.m.apply({key:3.});self.tick();self.n.allowed=False;self.tick();self.assertEqual(l.phase,'done');self.assertEqual(self.n.rate,10.);self.assertEqual([x[0] for x in self.n.native],['add','remove'])
    def test_factory_routes_existing_slider(self):
        k,key=self.setup_backend('shield_idle_delay',.7);calls=[];self.m.make_native_resource_rate=lambda *a,**kw:calls.append((a,kw)) or 'lane'
        self.assertEqual(self.m.make_automation_lane(k,None),'lane');self.assertEqual(calls,[(('shield_idle_delay',.7),{'persistent':True})])
    def test_compact_recovery_backend_selector(self):
        m=self.m;self.n.base.open();m._category=6;m._compact_view=True;m.draw();labels=self.n.base.gui.imgui.labels
        self.assertEqual(sum(x.endswith('##native_shield_pool_backend') for x in labels),1)
        for key in m.SHIELD_POOL_KEYS.values():self.assertEqual(sum(x.endswith('##'+key) for x in labels),1)
    def test_legacy_backend_skips_native_factory(self):
        k,key=self.setup_backend();m=self.m;m.SHIELD_POOL_BACKEND.value=False;m.automation_permitted=lambda:True
        calls=[];m.make_automation_lane=lambda *args:calls.append(args)
        self.tick();self.assertEqual(calls,[]);self.assertNotIn(k,m._automation_leases)
