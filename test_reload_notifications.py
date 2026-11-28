"""Paired native reload notifications: synthetic event ordering only."""
from test_automation_r28 import SwapReload
from test_combat_r13 import Node
EVENT_OWNER="/Script/OakGame.OakUIDataCollector_WeaponStatus"

class ReloadNotifications(SwapReload):
    def setUp(self):
        super().setUp()
        self.a.event_live=lambda:True
        self.collector=Node(Name='local weapon status',Class=Node(Name=EVENT_OWNER))
    def start_event(self,collector=None,weapon=None):
        self.a.observe_reload(collector or self.collector,weapon or self.r.w,True,True)
    def end_event(self,completed=True,collector=None,weapon=None):
        self.a.observe_reload(collector or self.collector,weapon or self.r.w,completed,False)
    def finish_fast(self):
        self.tick(8,'Active');self.tick(8,'Active')
    def test_between_polls(self):
        self.empty();self.start_event();self.end_event();self.finish_fast()
        self.assertIsNotNone(self.a.record);self.assertFalse(self.a.waiting)
        self.empty();self.assertEqual(len(self.r.calls),2)
    def test_synchronous_completion(self):
        def request(*args):
            self.r.calls.append(args);self.start_event()
            self.r.loaded=self.r.pool.LoadedAmmo=self.r.pool.ServerSyncedLoadedAmmo=8
            self.end_event()
        request.func=self.r.fn;self.r.w.ServerStartReloading=request
        self.empty();self.assertTrue(self.a.waiting);self.finish_fast()
        self.assertIsNotNone(self.a.record);self.assertFalse(self.a.waiting)
    def test_end_alone_refused(self):
        self.empty();self.end_event();self.finish_fast();self.assertIsNone(self.a.record)
    def test_cancel_refused(self):
        self.empty();self.start_event();self.end_event(False);self.finish_fast();self.assertIsNone(self.a.record)
    def test_foreign_collector_refused(self):
        self.empty();self.start_event();self.end_event(collector=Node(Name='other',Class=self.collector.Class));self.finish_fast();self.assertIsNone(self.a.record)
    def test_foreign_weapon_refused(self):
        self.empty();self.start_event(weapon=Node());self.end_event();self.finish_fast();self.assertIsNone(self.a.record)
    def test_duplicate_start_refused(self):
        self.empty();self.start_event();self.start_event();self.end_event();self.finish_fast();self.assertIsNone(self.a.record)
    def test_hook_loss_refused(self):
        self.empty();self.start_event();self.end_event();self.a.event_live=lambda:False;self.finish_fast();self.assertIsNone(self.a.record)
    def test_join_no_rearm(self):
        self.empty();self.start_event();self.end_event();self.r.b.f.players=2;self.finish_fast();self.assertIsNone(self.a.record)
    def test_swap_no_rearm(self):
        self.empty();self.start_event();self.end_event();self.swap();self.finish_fast();self.assertIsNone(self.a.record)
    def test_stale_event_not_next_cycle(self):
        self.empty();self.start_event();self.end_event();self.finish_fast();self.empty();self.finish_fast();self.assertIsNone(self.a.record)
    def test_registration_missing_keeps_polling(self):
        self.assertFalse(self.r.m._reload_observers_owned);self.a.event_live=lambda:False
        self.empty();self.complete();self.assertIsNotNone(self.a.record);self.assertFalse(self.a.waiting)
    def bind_observers(self):
        m=self.r.m
        self.r.b.f.sdk.hooks.Type.POST="POST"
        from bl4_custom_foundation.reload_assist import EVENTS
        for n,flag in EVENTS.items():
            ps=[type('ZObjectProperty',(),{'Name':'EventWeapon','ArrayDim':1,'PropertyClass':Node(Name='/Script/GbxWeapon.Weapon')})(),type('ZBoolProperty',(),{'Name':flag,'ArrayDim':1})()]
            self.r.funcs.append(Node(Name=n,Outer=Node(Name=EVENT_OWNER),NumParams=2,_path_name=lambda n=n:EVENT_OWNER+':'+n,_properties=lambda ps=ps:ps))
        m._reload_observers_attempted=False
    def test_registration_and_callback_delivery(self):
        self.bind_observers();m=self.r.m;self.assertTrue(m.ensure_reload_observers(self.r.b.f.sdk))
        self.a.event_live=m.reload_observers_live;m._automation_leases['reload']=self.a;m.automation_permitted=lambda:True
        self.empty();h=self.r.b.hooks;t=self.r.b.f.sdk.hooks.Type.POST
        h[(EVENT_OWNER+':OnReloadStarted',t,'bl4_custom_reload_observe_OnReloadStarted')](self.collector,Node(EventWeapon=self.r.w,bAutoReload=True))
        h[(EVENT_OWNER+':OnReloadEnded',t,'bl4_custom_reload_observe_OnReloadEnded')](self.collector,Node(EventWeapon=self.r.w,bCompleted=True))
        self.finish_fast();self.assertIsNotNone(self.a.record);self.assertFalse(self.a.waiting)
    def test_registration_bad_descriptor(self):
        self.bind_observers();self.r.funcs[-1].NumParams=3
        self.assertFalse(self.r.m.ensure_reload_observers(self.r.b.f.sdk))
        self.assertFalse(self.r.m._reload_observers_owned)
    def test_registration_preexisting_not_adopted(self):
        self.bind_observers();h=self.r.b.hooks;t=self.r.b.f.sdk.hooks.Type.POST;k=(EVENT_OWNER+':OnReloadEnded',t,'bl4_custom_reload_observe_OnReloadEnded');foreign=object();h[k]=foreign
        self.assertFalse(self.r.m.ensure_reload_observers(self.r.b.f.sdk));self.assertIs(h[k],foreign)
    def test_partial_registration_refused(self):
        self.bind_observers();hooks=self.r.b.f.sdk.hooks;original=hooks.add_hook
        hooks.add_hook=lambda p,*args: False if p.endswith('OnReloadEnded') else original(p,*args)
        self.assertFalse(self.r.m.ensure_reload_observers(self.r.b.f.sdk));self.assertFalse(self.r.m._reload_observers_owned)

    # Independent integration of Antigravity 692bd3c's transition-only finding.
    def test_equipping_putting_down_benign_wait(self):
        for state in ('PuttingDown','Equipping'):
            self.tick(state=state)
            self.assertIsNotNone(self.a.record)
            self.assertTrue(self.a.swap_paused)
            self.assertFalse(self.r.calls)
        self.tick(4,'Active');self.tick(4,'Active');self.empty()
        self.assertEqual(len(self.r.calls),1)
    def test_unrecognized_transition_still_stops(self):
        self.tick(state='CorruptedUnknownState')
        self.assertIsNone(self.a.record);self.assertFalse(self.r.calls)
    def test_transition_during_outstanding_request_never_discards_receipt(self):
        self.empty();self.start_event();self.tick(state='PuttingDown')
        self.assertIsNone(self.a.record);self.assertEqual(len(self.r.calls),1)
    def test_arming_in_transition_waits_for_idle(self):
        self.a.stop('test rearm');self.r.w.CurrentState='Equipping'
        self.assertTrue(self.a.begin());self.assertTrue(self.a.swap_paused)
        self.tick(0,'Equipping');self.assertFalse(self.r.calls)
        self.tick(4,'Active');self.tick(4,'Active');self.empty()
        self.assertEqual(len(self.r.calls),1)
