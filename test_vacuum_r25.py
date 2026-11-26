"""Synthetic lease and independent classification, never native gameplay."""
import unittest, struct
from types import SimpleNamespace as N
from test_foundation import Test

class Obj:
    def __init__(self,path,**kw):self.path=path;self.__dict__.update(kw)
    def _path_name(self):return self.path
    def _get_address(self):return id(self)

class VacuumTests(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown)
        from bl4_custom_foundation import loot_vacuum as v
        self.v=v;self.now=100.;self.thread=1;self.ok=True;self.calls=[];self.messages=[];self.actors=[];self.machines=[]
        self.lev=Obj('level',Class=Obj('/Script/Engine.Level'))
        self.pc=Obj('pc');self.state=Obj('state');self.pawn=self.actor('player',pos=(0,0,0));self.pawn.HealthCondition=N(name='Healthy');self.pawn.CharacterMovement=N(IsMovingOnGround=lambda:True)
        self.a=self.drop('a','ammo',(300,0,0));self.actors=[self.a]
    def func(self,path,sig,call):
        props=[]
        for n,t,target in sig:
            p=type(t,(),{'Name':n,'ArrayDim':1})();p.Struct=Obj(target);props.append(p)
        def f(*args):return call(*args)
        f.func=Obj(path,NumParams=len(props),_properties=lambda:props);return f
    def actor(self,name,pos):
        v=self.v
        o=Obj(name,Class=Obj(v.PICKUP),Outer=self.lev,Owner=None,bHidden=False,IsActorBeingDestroyed=lambda:False,HasAuthority=lambda:True,UsableActorState=N(bInteractabilityLockedReplicated=False))
        o.pos=pos;o.RootPrimitiveComponent=N(Outer=o)
        o.K2_GetActorLocation=self.func(v.LOCATION,v.LOC_SIG,lambda:N(**dict(zip('XYZ',o.pos))))
        o.K2_GetActorRotation=self.func(v.ROTATION,v.ROT_SIG,lambda:'rotation')
        o.K2_TeleportTo=self.func(v.TELEPORT,v.TP_SIG,lambda target,rot:self.move(o,target,rot))
        return o
    def move(self,o,target,rot):self.calls.append((o.path,(target.X,target.Y,target.Z),rot));return True
    def drop(self,name,kind,pos):
        a=self.actor(name,pos);path='/Game/Gear/Guns/Gun.Gun' if kind=='gear' else '/Game/Pickups/'+kind.title()+'/Body.Body'
        a.BodyData=Obj(path);color=next(c for k,c in self.v.PALETTE if k==kind)
        a.AttractEffectComponent=N(OverrideParameters=N(ParameterData=struct.pack('<4f',*color),SortedParameterOffsets=[N(Name='User.Color',Offset=0)]));return a
    def start(self,kinds=('ammo',),radius=30):
        self.lease=self.v.Vacuum(lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda k,**kw:self.actors if k=='InventoryPickup' else self.machines,lambda n,**kw:N(**kw),lambda:self.now,lambda:self.thread,self.messages.append,kinds,radius)
        return self.lease.begin()
    def tick(self,dt=.6,permitted=True):self.now+=dt;self.lease.tick(permitted)
    def test_contact(self):self.assertTrue(self.start());self.tick();self.assertEqual(self.calls,[('a',(0,0,-40),'rotation')])
    def test_filter(self):
        self.actors += [self.drop(k,k,(400,0,0)) for k in ('cash','eridium','health','gear')];self.start();self.tick();self.assertEqual(len(self.calls),1)
    def test_all(self):
        self.actors += [self.drop(k,k,(400,0,0)) for k in ('cash','eridium','health','gear')];self.start(self.v.CATEGORIES);self.tick();self.tick();self.assertEqual({c[0] for c in self.calls},{'a','cash','eridium','health','gear'});g=next(c for c in self.calls if c[0]=='gear');self.assertAlmostEqual(sum(x*x for x in g[1]),200**2)
    def test_unknown(self):self.a.BodyData=Obj('/Game/Pickups/Unknown');self.start();self.tick();self.assertFalse(self.calls)
    def test_color_disagree(self):self.a.BodyData=Obj('/Game/Pickups/Health');self.start();self.tick();self.assertFalse(self.calls)
    def test_mission(self):self.a.BodyData=Obj('/Game/Pickups/MissionAmmo');self.start();self.tick();self.assertFalse(self.calls)
    def test_duplicate_color(self):self.a.AttractEffectComponent.OverrideParameters.SortedParameterOffsets*=2;self.start();self.tick();self.assertFalse(self.calls)
    def test_repeat(self):self.start();self.tick();self.tick();self.assertEqual(len(self.calls),1)
    def test_radius(self):self.a.pos=(501,0,0);self.start(radius=5);self.tick();self.assertFalse(self.calls)
    def test_unowned_required(self):self.a.Owner=Obj('other');self.start();self.tick();self.assertFalse(self.calls)
    def test_wrong_level(self):self.a.Outer=Obj('otherlevel',Class=Obj('/Script/Engine.Level'));self.start();self.tick();self.assertFalse(self.calls)
    def test_locked(self):self.a.UsableActorState.bInteractabilityLockedReplicated=True;self.start();self.tick();self.assertFalse(self.calls)
    def test_vendor(self):m=self.actor('vendor',(301,0,0));m.GetIOTDForPlayer=lambda pc:self.a;self.machines=[m];self.start();self.tick();self.assertFalse(self.calls)
    def test_no_categories(self):self.assertFalse(self.start(()));self.tick();self.assertFalse(self.calls)
    def test_bad_radius(self):self.assertFalse(self.start(radius=float('nan')))
    def test_join(self):self.start();self.ok=False;self.tick();self.assertIsNone(self.lease.record);self.assertFalse(self.calls)
    def test_permission(self):self.start();self.tick(permitted=False);self.assertIsNone(self.lease.record);self.assertFalse(self.calls)
    def test_expiry(self):self.start();self.tick(31);self.assertFalse(self.calls)
    def test_airborne(self):self.pawn.CharacterMovement.IsMovingOnGround=lambda:False;self.assertFalse(self.start())
    def test_refused_once(self):self.move=lambda *a:self.calls.append(a) or False;self.start();self.tick();self.tick();self.assertEqual(len(self.calls),1);self.assertEqual(self.lease.moved,0)
    def test_fault(self):
        def boom(*a):raise RuntimeError('unknown native result')
        self.move=boom;self.start();self.tick();self.assertTrue(self.lease.fault);self.assertIsNone(self.lease.record)
    def test_signature(self):self.a.K2_TeleportTo.func.NumParams=99;self.start();self.tick();self.assertFalse(self.calls);self.assertIsNone(self.lease.record)
    def test_batch_limit(self):
        self.actors=[self.drop(str(i),'ammo',(300+i,0,0)) for i in range(30)];self.start();self.tick();self.assertEqual(len(self.calls),4)
        for _ in range(10):self.tick()
        self.assertEqual(len(self.calls),24);self.assertIsNone(self.lease.record)
    def test_stop_during_read(self):
        self.start();old=self.a.K2_GetActorRotation
        def stop():self.lease.stop('owner stop');return old()
        stop.func=old.func;self.a.K2_GetActorRotation=stop;self.tick();self.assertFalse(self.calls)
    def test_ui_filters_defaults_and_reset(self):
        m=self.base.m;self.assertFalse(any(m._vacuum_filters.values()));m._vacuum_filters['ammo']=True;m.reset();self.assertFalse(any(m._vacuum_filters.values()));self.assertEqual(m._vacuum_radius,30.)
    def test_f8_filter_selection(self):
        m=self.base.m; self.base.open();m._category=5
        self.base.gui.imgui.edits={'Vacuum ammo##vacuum_ammo':True,'Pickup radius##vacuum_radius':45.}
        queued=[];m.activate_feature=lambda *a:queued.append(a);m.draw();self.assertFalse(queued)
        self.base.gui.imgui.clicks={'Arm experimental Loot Vacuum (30 sec)'};m.draw();self.assertEqual(queued,[('loot_vacuum',(('ammo',),45.))])
    def test_f8_compact(self):
        m=self.base.m;self.base.open();m._category=5;m._compact_view=True;m.draw();self.assertIn('Vacuum gear##vacuum_gear',self.base.gui.imgui.labels)
    def test_foreign_mission_gear(self):
        self.assertIsNone(self.v.body_kind('/Game/Gear/Mission/Weapon'))
