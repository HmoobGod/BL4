"""Mock native request lifecycle. Never executes the native request."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Combat, Node, attr

class ReloadEvent(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.f=self.c.b.f;self.f.solo=True
        self.m.close_menu();self.c.b.gui.finish_close()
        self.now=100.;self.m.time=N(monotonic=lambda:self.now)
        self.hooks=self.f.sdk.hooks;self.hooks.Type.PRE='pre'
        from bl4_custom_foundation.reload_assist import REQUEST,REQUEST_SIG
        self.path=REQUEST
        self.fn=Node(Name='ServerStartReloading',NumParams=2,_path_name=lambda:REQUEST,
                     Outer=Node(_path_name=lambda:REQUEST.rsplit(':',1)[0]),
                     _properties=lambda:[type(t,(),{'Name':n,'ArrayDim':1})() for n,t in REQUEST_SIG])
        self.f.funcs.append(self.fn)
        self.args=N(UseModeIndex=0,Flags_0=0)
        self.m.apply({'persistent_master':True,'persistent_offline':True,'persistent_reload':True,'reload':2.,'persistent_reload_event_window':True})
    def tick(self,dt=.01):self.now+=dt;self.m.monitor_tick()
    def arm(self):
        self.tick();self.assertTrue(self.m._reload_event_registered);self.assertEqual(self.c.reload.writes,[])
    def pre(self,obj=None,args=None):return self.m.reload_event_pre(obj or self.c.w,args or self.args,None,self.fn)
    def post(self,obj=None):return self.m.reload_event_post(obj or self.c.w,self.args,None,self.fn)
    def test_event_transaction_no_request_replay(self):
        self.arm();self.assertIsNone(self.pre());self.assertEqual(self.c.reload.Value,1.5)
        self.c.w.CurrentState='Reloading';self.assertIsNone(self.post());self.assertEqual(self.c.reload.Value,3.)
        self.assertFalse(self.m._reload_event.fault);self.assertFalse(self.m._reload_event.controller.records)
    def test_no_steady_state_mutation(self):
        self.arm()
        for _ in range(30):self.tick(.1)
        self.assertEqual(self.c.reload.writes,[])
        self.assertNotIn('reload',self.m.auto_desired())
    def test_foreign_mode_flags_and_owner_refused(self):
        self.arm();self.pre(Node());self.pre(args=N(UseModeIndex=1,Flags_0=0));self.pre(args=N(UseModeIndex=0,Flags_0=1));self.c.w.Owner=Node();self.pre()
        self.assertEqual(self.c.reload.writes,[])
    def test_floor_refusal_not_reported_as_restore(self):
        self.c.minimum._values.update(Value=2.,BaseValue=2.);self.arm();self.pre();self.post();self.assertEqual(self.c.reload.writes,[])
        self.assertIn('admission rejected',self.m._reload_event.last_result)
    def test_nested_post_does_not_restore_early(self):
        self.arm();self.pre();foreign=Node();self.pre(foreign);self.post(foreign);self.assertEqual(self.c.reload.Value,1.5);self.post();self.assertEqual(self.c.reload.Value,3.)
    def test_swap_fresh_weapon_no_wait(self):
        self.arm();self.pre();self.post();newrate=attr(4.);new=self.c.weapon(attr(8.),newrate,attr(.5));self.c.p.ActiveWeapons.Slots.append(self.c.slot(new));self.c.w.CurrentState='Inactive';self.pre(new);self.assertEqual(newrate.Value,2.);self.post(new);self.assertEqual(newrate.Value,4.)
    def test_join_during_request_still_restores(self):
        self.arm();self.pre();self.f.players=2;self.post();self.assertEqual(self.c.reload.Value,3.);self.pre();self.assertEqual(self.c.reload.Value,3.)
    def test_missing_post_watchdog(self):
        self.arm();self.pre();self.tick(.6);self.assertEqual(self.c.reload.Value,3.);self.assertTrue(self.m._reload_event.disabled);self.pre();self.assertEqual(self.c.reload.Value,3.)
    def test_foreign_drift_fault(self):
        self.arm();self.pre();self.c.reload._values['Value']=1.8;self.post();self.assertEqual(self.c.reload.Value,1.8);self.assertTrue(self.m.automation_fault())
    def test_disabled_or_automatic_lane_no_event_writes(self):
        self.arm();self.m.AUTO_OPTIONS['reload'].value=False;self.pre();self.m.AUTO_OPTIONS['reload'].value=True;self.m.AUTOMATION_OPTIONS['reload'].value=True;self.pre();self.assertEqual(self.c.reload.writes,[])
    def test_wrong_signature_no_hooks(self):
        self.fn.NumParams=1;self.tick();self.assertFalse(self.m._reload_event_registered);self.assertEqual(self.c.reload.writes,[])
    def test_missing_cleanup_hook_no_writes(self):
        self.arm();del self.c.b.hooks[self.path,'post','bl4_custom_reload_window_post'];self.pre();self.assertEqual(self.c.reload.writes,[])
    def test_movement_peer_not_restored_by_reload_event(self):
        self.m.apply({'persistent_repair_health':True,'repair_health':2.});self.arm();self.assertEqual(self.c.health.Value,40.);self.pre();self.post();self.assertEqual(self.c.health.Value,40.)
    def test_default_legacy_preserved(self):
        self.m.RELOAD_EVENT.value=False;self.tick();self.assertFalse(self.m._reload_event_registered);self.assertEqual(self.c.reload.Value,1.5)
    def test_switch_to_event_restores_previous_lease(self):
        self.m.RELOAD_EVENT.value=False;self.tick();self.assertEqual(self.c.reload.Value,1.5);self.m.set_auto_setting(self.m.RELOAD_EVENT,True);self.tick(.3);self.assertEqual(self.c.reload.Value,3.);self.pre();self.assertEqual(self.c.reload.Value,1.5);self.post();self.assertEqual(self.c.reload.Value,3.)
    def test_nested_post_during_apply_does_not_leak_depth(self):
        self.arm();self.pre();self.m._reload_event.busy=True;self.pre();self.post();self.m._reload_event.busy=False
        self.assertEqual(self.m._reload_event.depth,1);self.post();self.assertEqual(self.c.reload.Value,3.)
    def test_alias_with_peer_refused(self):
        self.arm();from bl4_custom_foundation.gameplay_fields import describe_fields
        from bl4_custom_foundation.weapon_rates import fields
        tokens=describe_fields(fields(self.c.w.behaviors[1],'reload'))[1]
        self.m._reload_event.peer_tokens=lambda:tokens;self.pre();self.post();self.assertEqual(self.c.reload.writes,[])
