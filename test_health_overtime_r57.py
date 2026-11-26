"""Synthetic native timed flesh experiment; not a native gameplay test."""
from types import SimpleNamespace as N
from test_health_pulse_r17 import HealthPulse

class NativeTimedHealth(HealthPulse):
    def setUp(self):
        super().setUp()
        from bl4_custom_foundation.health_pulse import OVERTIME_NAME, OVERTIME_SPEC
        self.timed_calls=[];self.overtime=OVERTIME_NAME
        ps=[type(k,(),{'Name':n,'ArrayDim':1})() for n,k in OVERTIME_SPEC]
        ps[0].PropertyClass=N(_path_name=lambda:'/Script/Engine.Actor')
        owner=N(_path_name=lambda:self.PATH[:-1],ClassDefaultObject=N())
        self.fn=N(Name=self.overtime,Outer=owner,NumParams=len(ps),_path_name=lambda:self.PATH+self.overtime,_properties=lambda:ps)
        self.set_call(self.native)
        self.funcs.append(self.fn)
    def set_call(self,call):
        def bound(*args):return call(*args)
        bound.func=self.fn;setattr(self.fn.Outer.ClassDefaultObject,self.overtime,bound)
    def native(self,*args):
        self.timed_calls.append(args);return 17
    def start(self):self.m.activate_feature('health_overtime',1.);self.m.monitor_tick()
    def after(self,p=.51):self.pct=p;self.cur._values['Value']=100*p
    def test_one_native_timed_call(self):
        self.start();self.assertTrue(self.m.health_active());self.assertFalse(self.timed_calls)
        self.advance();self.assertEqual(len(self.timed_calls),1)
        pawn,h,amount,cap,duration,tick=self.timed_calls[0];self.assertIs(pawn,self.p);self.assertIs(h,self.hp);self.assertAlmostEqual(amount,.01);self.assertAlmostEqual(cap,.51);self.assertEqual((duration,tick),(2.,.5))
        self.assertFalse(self.calls);self.after();self.advance();self.advance();self.advance(.5)
        self.assertFalse(self.m.health_active());self.assertFalse(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
        self.start();self.assertFalse(self.m.health_active());self.assertEqual(len(self.timed_calls),1)
    def test_join_before_dispatch(self):
        self.start();self.b.f.players=2;self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_join_after_dispatch_fault(self):
        self.start();self.advance();self.b.f.players=2;self.advance();self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_stop_before_dispatch(self):
        self.start();self.m.request_stop('restore');self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_fault())
    def test_stop_after_dispatch_fault(self):
        self.start();self.advance();self.m.request_stop('restore');self.advance();self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_full_no_dispatch(self):
        self.after(1.);self.start();self.advance();self.assertFalse(self.m.health_active());self.assertFalse(self.timed_calls)
    def test_bad_signature(self):
        self.fn.NumParams-=1;self.start();self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_missing_native_function(self):
        self.funcs.pop();self.start();self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_bad_id_fault(self):
        self.set_call(lambda *a:0);self.start();self.advance();self.assertTrue(self.m.health_fault())
    def test_late_callback_no_dispatch(self):
        self.start();self.advance(3.);self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_no_effect_fault(self):
        self.start();self.advance();self.advance(2.5);self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_overcap_fault(self):
        self.start();self.advance();self.after(.6);self.advance();self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_f8_queue(self):
        self.m._category=6;self.b.gui.imgui.clicks={'Test native timed flesh recovery (2 sec)'};self.m.draw();self.assertFalse(self.m.health_active());self.assertFalse(self.timed_calls);self.m.monitor_tick();self.assertTrue(self.m.health_active());self.advance();self.assertEqual(len(self.timed_calls),1)
    def test_stop_inside_getter(self):
        self.start();lease=self.m._health_pulse
        def read(*args):self.m.request_stop('reentrant');return self.pct
        lease.api=(self.layer,read,lease.api[2]);self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_changed_health_handle(self):
        self.start();self.hp._name='HealthType_Replacement';self.advance();self.assertFalse(self.timed_calls)
    def test_reentrant_stop_during_call(self):
        def call(*args):self.timed_calls.append(args);self.m.request_stop('during call');return 17
        self.set_call(call);self.start();self.advance();self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_dispatch_exception_fault(self):
        def call(*args):self.timed_calls.append(args);raise RuntimeError('unknown native outcome')
        self.set_call(call);self.start();self.advance();self.assertTrue(self.m.health_fault());self.assertEqual(len(self.timed_calls),1)
    def test_consent_lost_during_getter(self):
        self.start();lease=self.m._health_pulse
        def read(*args):self.m._offline_confirmed=False;return self.pct
        lease.api=(self.layer,read,lease.api[2]);self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
    def test_master_change_during_getter(self):
        self.start();lease=self.m._health_pulse
        def read(*args):self.m.auto_master.value=True;return self.pct
        lease.api=(self.layer,read,lease.api[2]);self.advance();self.assertFalse(self.timed_calls);self.assertFalse(self.m.health_active())
