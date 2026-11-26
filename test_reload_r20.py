"""Synthetic normal reload path: local ownership, binding, one-shot lifecycle."""
import unittest
from types import SimpleNamespace as N
from test_combat_r13 import Combat,Node,typ,desc

class ReloadTests(unittest.TestCase):
    def setUp(self):
        self.c=Combat();self.c.setUp();self.addCleanup(self.c.doCleanups)
        self.m=self.c.m;self.p=self.c.p;self.w=self.c.w;self.b=self.c.b
        self.now=100.;self.calls=[];self.m.time=N(monotonic=lambda:self.now)
        self.p.HealthCondition=N(name='Healthy');self.authority=True
        def ip(n):return type('ZIntProperty',(),{'Name':n,'ArrayDim':1})()
        ma=Node(_type=typ('GbxAttributeInteger',ip('Value')),Value=8)
        self.pool=Node(Name='UM0_AmmoPool',Outer=self.w,MaxLoadedAmmo=ma,LoadedAmmo=4,StoredAmmo=20,SpareAmmo=20,ServerSyncedLoadedAmmo=4,Class=typ('WeaponBehavior_AmmoPool',desc('MaxLoadedAmmo',ma._type),*(ip(n) for n in ('LoadedAmmo','StoredAmmo','SpareAmmo','ServerSyncedLoadedAmmo'))))
        self.w.behaviors.append(self.pool);self.loaded=4
        from bl4_custom_foundation.reload_assist import SPECS,PATH,REQUEST,REQUEST_SIG
        self.funcs=[]
        for name,sig in SPECS.items():
            props=[type(t,(),{'Name':n,'ArrayDim':1})() for n,t in sig];props[0].PropertyClass=Node(Name='/Script/Engine.Actor' if name=='IsLocalWeaponAuthority' else '/Script/GbxWeapon.Weapon')
            cdo=N();owner=Node(Name=PATH[:-1],ClassDefaultObject=cdo)
            f=Node(Name=name,Outer=owner,NumParams=len(props),_path_name=lambda n=name:PATH+n,_properties=lambda ps=props:ps)
            call={'GetLoadedAmmo':lambda w,i:self.loaded,'GetMaxLoadedAmmo':lambda w,i:8,'IsLocalWeaponAuthority':lambda p:self.authority}[name]
            def bound(*a,call=call):return call(*a)
            bound.func=f;setattr(cdo,name,bound);self.funcs.append(f)
        ps=[type(t,(),{'Name':n,'ArrayDim':1})() for n,t in REQUEST_SIG]
        self.fn=Node(Name='ServerStartReloading',Outer=Node(Name=REQUEST.rsplit(':',1)[0]),NumParams=2,_path_name=lambda:REQUEST,_properties=lambda:ps)
        self.funcs.append(self.fn)
        def request(i,flags):self.calls.append((i,flags))
        request.func=self.fn;self.w.ServerStartReloading=request
        old=self.b.f.sdk.find_all;self.b.f.sdk.find_all=lambda *a,**k:list(old(*a,**k))+self.funcs if a[0]=='Function' else old(*a,**k)
    def start(self):self.m.activate_feature('reload_assist',1.);self.m.monitor_tick()
    def advance(self,loaded=None,dt=.2,state=None):
        if loaded is not None:self.loaded=self.pool.LoadedAmmo=self.pool.ServerSyncedLoadedAmmo=loaded
        if state is not None:self.w.CurrentState=state
        self.now+=dt;self.m.monitor_tick()
    def empty(self):self.advance(0,state='Firing');self.advance(state='Active')
    def test_native_once(self):self.start();self.assertTrue(self.m.health_active());self.empty();self.assertEqual(self.calls,[(0,0)]);self.assertFalse(self.m.health_active());self.advance(4);self.empty();self.assertEqual(len(self.calls),1)
    def test_no_startup_or_loaded_request(self):self.assertEqual(self.calls,[]);self.start();self.advance(3);self.advance(2);self.assertEqual(self.calls,[])
    def test_initial_empty(self):self.advance(0);self.start();self.assertFalse(self.m.health_active());self.assertEqual(self.calls,[])
    def test_not_idle(self):self.w.CurrentState='Firing';self.start();self.assertFalse(self.m.health_active())
    def test_no_reserve(self):self.start();self.pool.SpareAmmo=0;self.empty();self.assertEqual(self.calls,[])
    def test_reserve_initial(self):self.pool.StoredAmmo=0;self.start();self.assertFalse(self.m.health_active())
    def test_wrong_owner(self):self.start();self.w.Owner=Node();self.empty();self.assertEqual(self.calls,[])
    def test_ordnance(self):self.w.Class.Name='HeavyWeaponGadget';self.start();self.assertFalse(self.m.health_active())
    def test_join(self):self.start();self.advance(0);self.b.f.players=2;self.advance();self.assertEqual(self.calls,[])
    def test_mode_changed(self):self.start();self.advance(0);self.w.CurrentUseModeIndex=1;self.advance();self.assertEqual(self.calls,[])
    def test_pending_weapon(self):self.start();self.advance(0);self.p.ActiveWeapons.Slots[0].PendingWeapon=self.w;self.advance();self.assertEqual(self.calls,[])
    def test_pool_disagree(self):self.start();self.advance(0);self.pool.ServerSyncedLoadedAmmo=1;self.advance();self.assertEqual(self.calls,[])
    def test_binding_missing(self):self.funcs.pop();self.start();self.assertFalse(self.m.health_active())
    def test_bound_replacement(self):self.start();self.advance(0);self.w.ServerStartReloading=lambda *a:self.calls.append(a);self.advance();self.assertEqual(self.calls,[])
    def test_native_already_reloading(self):self.start();self.advance(0,state='Reloading');self.advance(state='Active');self.assertEqual(self.calls,[])
    def test_no_dispatch_while_firing(self):self.start();self.advance(0,state='Firing');self.advance();self.assertEqual(self.calls,[]);self.advance(state='Active');self.assertEqual(len(self.calls),1)
    def test_expiry(self):self.start();self.advance(0);self.advance(dt=30);self.assertEqual(self.calls,[])
    def test_stop(self):self.start();self.advance(0);self.m.request_stop('owner');self.advance();self.assertEqual(self.calls,[])
    def test_master(self):self.start();self.advance(0);self.m.set_auto_setting(self.m.auto_master,True);self.advance();self.assertEqual(self.calls,[])
    def test_authority(self):self.start();self.authority=False;self.empty();self.assertEqual(self.calls,[])
    def test_fault(self):
        def request(*a):raise RuntimeError('unknown result')
        request.func=self.fn;self.w.ServerStartReloading=request;self.start();self.empty();self.assertTrue(self.m.health_fault());self.assertFalse(self.m.health_active())
    def test_reentrant_tick(self):
        def request(*a):self.calls.append(a);self.m.monitor_tick()
        request.func=self.fn;self.w.ServerStartReloading=request;self.start();self.empty();self.assertEqual(len(self.calls),1)
    def test_reentrant_stop(self):
        self.start();self.advance(0);a=self.m._health_pulse;old=a.api[0]
        def read(*x):self.m.request_stop('reentrant');return old(*x)
        a.api=(read,*a.api[1:]);self.advance();self.assertEqual(self.calls,[])
    def test_f8(self):self.m._category=5;self.b.gui.imgui.clicks={'Arm experimental automatic reload (30 sec)'};self.m.draw();self.assertFalse(self.m.health_active());self.m.monitor_tick();self.assertTrue(self.m.health_active())
    def test_other_modifier(self):self.c.activate('jump',1.5);self.start();self.assertFalse(self.m.health_active())
