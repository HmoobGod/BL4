"""Synthetic start/stop lifecycle, no game execution or native ABI certification."""
from types import SimpleNamespace as N
from test_health_pulse_r17 import HealthPulse, FGameDataHandle
from test_combat_r13 import Node, typ, desc, arraydesc


def prop(n,k):return type(k,(),{'Name':n,'ArrayDim':1})()
def fulltype(name,path,*props):
    t=typ(name,*props);t._path_name=lambda:path;return t
class FGbxDefPtr(Node):pass

class NativeRegenTest(HealthPulse):
    def setUp(self):
        super().setUp()
        from bl4_custom_foundation.health_pulse import INIT,TAG_CONTAINER,TAG,REGEN_SPECS
        self.native=[];self.stop_calls=[]
        self.tag=fulltype('GameplayTag',TAG,prop('TagName','ZNameProperty'))
        self.tags=fulltype('GameplayTagContainer',TAG_CONTAINER,arraydesc('GameplayTags',desc('inner',self.tag)),arraydesc('ParentTags',desc('inner',self.tag)))
        self.hp.GameplayTags=self.tagset('Health.Flesh');self.sh.GameplayTags=self.tagset('Health.Shield')
        self.table=typ('DataTableValueHandle',prop('DataTable','ZGbxDefPtrProperty'),prop('RowName','ZNameProperty'),prop('ColumnName','ZNameProperty'))
        self.init=fulltype('GbxAttributeInit',INIT,prop('constant','ZFloatProperty'),prop('PostScale','ZFloatProperty'),prop('attribute','ZGameDataHandleProperty'),desc('DataTableValue',self.table))
        self.b.f.sdk.unreal.FGbxDefPtr=FGbxDefPtr
        self.b.f.sdk.make_struct=self.make
        self.constructed=[];self.start_fn=None;self.stop_fn=None
        for name,sig in REGEN_SPECS.items():
            ps=[prop(n,k) for n,k in sig];ps[0].PropertyClass=N(_path_name=lambda:'/Script/Engine.Actor')
            if name=='StartHealthRegen':ps[2].Struct=self.init;ps[5].Struct=self.tags
            owner=N(_path_name=lambda:self.PATH[:-1],ClassDefaultObject=N())
            fn=N(Name=name,Outer=owner,NumParams=len(ps),_path_name=lambda name=name:self.PATH+name,_properties=lambda ps=ps:ps)
            self.funcs.append(fn)
            self.set_bound(fn,self.start_native if name=='StartHealthRegen' else self.stop_native)
            if name=='StartHealthRegen':self.start_fn=fn
            else:self.stop_fn=fn
    def tagset(self,name):
        return Node(_type=self.tags,GameplayTags=[Node(_type=self.tag,TagName=name)],ParentTags=[Node(_type=self.tag,TagName='Health')])
    def make(self,path,qualified,**kw):
        self.assertEqual(path,self.init._path_name());self.assertIs(qualified,True)
        a=FGameDataHandle('None',None,None);a._type_handle=0
        table=Node(_type=self.table,DataTable=FGbxDefPtr(_name='None',_type=None),RowName='None',ColumnName='None')
        rate=Node(_type=self.init,attribute=a,DataTableValue=table,**kw);self.constructed.append(rate);return rate
    def set_bound(self,fn,call):
        def f(*a):return call(*a)
        f.func=fn;setattr(fn.Outer.ClassDefaultObject,fn.Name,f)
    def start_native(self,*a):self.native.append(a);return 71
    def stop_native(self,*a):self.stop_calls.append(a)
    def start(self):self.m.activate_feature('health_regen_native',1.);self.m.monitor_tick()
    def test_native_start_stop(self):
        self.start();self.assertTrue(self.m.health_active());self.assertFalse(self.native);self.advance()
        self.assertEqual(len(self.native),1);p,d,r,full,t,tags=self.native[0]
        self.assertIs(p,self.p);self.assertEqual((d,full,t),(2.,True,.5));self.assertEqual((r.constant,r.PostScale),(.01,1.));self.assertIs(tags,self.hp.GameplayTags)
        self.pct=.51;self.cur._values['Value']=51.;self.advance();self.assertEqual(self.stop_calls,[(self.p,71)]);self.assertFalse(self.m.health_active());self.assertFalse(self.m.health_fault())
        self.assertFalse(self.calls);self.start();self.assertFalse(self.m.health_active());self.assertEqual(len(self.native),1)
    def test_shared_timed_attempt(self):
        self.m._native_overtime_used=True;self.start();self.advance();self.assertFalse(self.native)
    def test_missing_stop_binding(self):self.funcs.remove(self.stop_fn);self.start();self.advance();self.assertFalse(self.native)
    def test_invalid_initializer_type(self):self.start_fn._properties()[2].Struct=self.tags;self.start();self.advance();self.assertFalse(self.native)
    def test_wrong_tag_type(self):self.hp.GameplayTags._type=typ('BadTagType');self.start();self.advance();self.assertFalse(self.native)
    def test_peer_overlap(self):self.sh.GameplayTags=self.tagset('Health.Flesh.Child');self.start();self.advance();self.assertFalse(self.native)
    def test_peer_missing_tags(self):self.sh.GameplayTags.GameplayTags=[];self.start();self.advance();self.assertFalse(self.native)
    def test_multi_flesh_tags(self):self.hp.GameplayTags.GameplayTags.append(Node(_type=self.tag,TagName='Health.Other'));self.start();self.advance();self.assertFalse(self.native)
    def test_nonempty_attribute(self):
        def bad(*a,**kw):r=self.make(*a,**kw);r.attribute._name='SomeAttribute';return r
        self.b.f.sdk.make_struct=bad;self.start();self.advance();self.assertFalse(self.native)
    def test_nonempty_table(self):
        def bad(*a,**kw):r=self.make(*a,**kw);r.DataTableValue.RowName='SomeRow';return r
        self.b.f.sdk.make_struct=bad;self.start();self.advance();self.assertFalse(self.native)
    def test_tag_change_after_arming(self):self.start();self.hp.GameplayTags=self.tagset('Health.Replacement');self.advance();self.assertFalse(self.native)
    def test_stop_before_dispatch(self):self.start();self.m.request_stop('restore');self.advance();self.assertFalse(self.native);self.assertFalse(self.stop_calls)
    def test_stop_deferred(self):
        self.start();self.advance();self.m.request_stop('restore');self.assertFalse(self.stop_calls);self.advance(.1);self.assertEqual(self.stop_calls,[(self.p,71)]);self.assertFalse(self.m.health_active())
    def test_join_before_start(self):self.start();self.b.f.players=2;self.advance();self.assertFalse(self.native)
    def test_join_after_start(self):self.start();self.advance();self.b.f.players=2;self.advance(.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_expired_id_no_stop(self):self.start();self.advance();self.advance(2.);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_invalid_id_no_stop(self):self.set_bound(self.start_fn,lambda *a:0);self.start();self.advance();self.assertTrue(self.m.health_fault());self.assertFalse(self.stop_calls)
    def test_start_exception(self):
        def fail(*a):raise RuntimeError('uncertain')
        self.set_bound(self.start_fn,fail);self.start();self.advance();self.assertTrue(self.m.health_fault());self.assertFalse(self.stop_calls)
    def test_stop_exception(self):
        def fail(*a):raise RuntimeError('uncertain')
        self.set_bound(self.stop_fn,fail);self.start();self.advance();self.advance();self.assertTrue(self.m.health_fault())
    def test_reentrant_stop_in_start(self):
        def call(*a):self.native.append(a);self.m.request_stop('reentrant');return 71
        self.set_bound(self.start_fn,call);self.start();self.advance();self.assertFalse(self.stop_calls);self.advance(.1);self.assertEqual(self.stop_calls,[(self.p,71)])
    def test_late_consent_lost(self):
        self.start();lease=self.m._health_pulse
        def read(*a):self.m._offline_confirmed=False;return self.pct
        lease.api=(lease.api[0],read,*lease.api[2:]);self.advance();self.assertFalse(self.native)
    def test_f8_queue(self):
        self.m._category=6;self.b.gui.imgui.clicks={'Test native regeneration start/stop (2 sec)'};self.m.draw();self.assertFalse(self.native);self.m.monitor_tick();self.assertTrue(self.m.health_active());self.advance();self.assertEqual(len(self.native),1)
    def test_full_may_retire_id(self):
        self.start();self.advance();self.pct=1.;self.cur._values['Value']=100.;self.advance(.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_overshoot_stop_early(self):
        self.start();self.advance();self.pct=.6;self.cur._values['Value']=60.;self.advance(.1);self.assertEqual(self.stop_calls,[(self.p,71)]);self.assertFalse(self.m.health_active());self.assertTrue(self.m.health_fault())
    def test_replaced_pawn_no_cleanup(self):
        self.start();self.advance();self.b.f.pc.Pawn=Node();self.advance(.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_bad_parent_tag(self):
        self.hp.GameplayTags.ParentTags[0].TagName='Unrelated';self.start();self.advance();self.assertFalse(self.native)
    def test_cleanup_late_session_loss(self):
        self.start();self.advance();lease=self.m._health_pulse;old=lease.cleanup_context;count=[0]
        def ctx():
            count[0]+=1
            if count[0]==2:self.b.f.players=2
            return old()
        lease.cleanup_context=ctx;self.m.request_stop('restore');self.advance(.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
    def test_late_tag_change_before_start(self):
        self.start();lease=self.m._health_pulse;old=lease.context;count=[0]
        def ctx():
            count[0]+=1
            if count[0]==3:self.hp.GameplayTags=self.tagset('Health.LateReplacement')
            return old()
        lease.context=ctx;self.advance();self.assertFalse(self.native)
    def test_full_after_final_cleanup_scope(self):
        self.start();self.advance();lease=self.m._health_pulse;old=lease.cleanup_context;count=[0]
        def ctx():
            count[0]+=1
            if count[0]==2:self.pct=1.;self.cur._values['Value']=100.
            return old()
        lease.cleanup_context=ctx;self.m.request_stop('restore');self.advance(.1);self.assertFalse(self.stop_calls);self.assertTrue(self.m.health_fault())
