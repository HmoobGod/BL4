"""Synthetic second-jump dispatch, not native physics."""
import unittest
from test_combat_r13 import Node, typ, desc
from test_foundation import Test
GOAL_TYPE="/Script/GbxGame.JumpGoalDef"
VECTOR="/Script/CoreUObject.Vector"

def p(name,kind,**fields):return type(kind,(),dict(Name=name,ArrayDim=1,**fields))()
def t(name,path,*props):
    a=typ(name,*props);a._path_name=lambda:path;return a
class FGbxDefPtr(Node):pass
class JumpVelocity(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown)
        from bl4_custom_foundation.double_jump import DoubleJump
        self.now=0.;self.ok=True;self.tid=1;self.messages=[];self.pc=Node();self.state=Node()
        self.ground=True;self.fall=False;self.controlled=False
        self.goaltype=t('JumpGoalDef',GOAL_TYPE,p('InitialZVelocity','ZFloatProperty'),p('GoalHeight','ZFloatProperty'),p('bUseInitialZVelocity','ZBoolProperty'))
        self.goal=FGbxDefPtr(_type=self.goaltype,_name='JumpGoal_Default',InitialZVelocity=800.,GoalHeight=300.,bUseInitialZVelocity=True)
        self.details=Node(_type=t('JumpDetails','/Script/GbxGame.JumpDetails',p('JumpGoal','ZGbxDefPtrProperty',Struct=self.goaltype)),JumpGoal=self.goal)
        self.vel=Node(_type=t('Vector',VECTOR,*(p(k,'ZDoubleProperty') for k in 'XYZ')),X=30.,Y=40.,Z=0.)
        self.pawn=Node(Class=typ('OakCharacter',p('JumpCurrentCount','ZIntProperty')),Outer=Node(Class=t('Level','/Script/Engine.Level')),HealthCondition=Node(name='Healthy'),bHidden=False,IsActorBeingDestroyed=lambda:False,JumpCurrentCount=0)
        self.comp=Node(Class=typ('OakCharacterMovementComponent',p('JumpedCount','ZIntProperty'),p('bIsGliding','ZBoolProperty'),desc('CurrentJump',self.details._type),desc('Velocity',self.vel._type)),OakCharacterOwner=self.pawn,CharacterOwner=self.pawn,JumpedCount=0,bIsGliding=False,CurrentJump=self.details,Velocity=self.vel)
        self.pawn.CharacterMovement=self.comp
        for name,cls,field in [('IsMovingOnGround','/Script/Engine.NavMovementComponent','ground'),('IsFalling','/Script/Engine.NavMovementComponent','fall'),('IsPerformingControlledMove','/Script/GbxGame.GbxCharacterMovementComponent','controlled')]:
            f=lambda field=field:getattr(self,field)
            f.func=Node(NumParams=1,_path_name=lambda n=name,c=cls:c+':'+n,_properties=lambda:[p('ReturnValue','ZBoolProperty')]);setattr(self.comp,name,f)
        self.lane=DoubleJump(lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.now,lambda:self.tid,self.messages.append,1.5)
    def tick(self,dt=.06):self.now+=dt;self.lane.tick(True)
    def start(self):self.assertTrue(self.lane.begin());self.tick()
    def first(self):
        self.ground=False;self.fall=True;self.pawn.JumpCurrentCount=self.comp.JumpedCount=1;self.goal._name='JumpGoal_Default';self.vel.Z=800.;self.tick()
    def second(self,dt=.06):
        self.pawn.JumpCurrentCount=self.comp.JumpedCount=2;self.goal._name='JumpGoal_DoubleJump';self.vel.Z=800.;self.tick(dt)
    def test_one_per_cycle(self):
        self.start();self.first();self.assertEqual(self.vel.Z,800.);self.second();self.assertEqual((self.vel.X,self.vel.Y,self.vel.Z),(30.,40.,1200.));self.tick();self.assertEqual(self.vel.Z,1200.);self.assertEqual(self.lane.applied,1)
        self.ground=True;self.fall=False;self.pawn.JumpCurrentCount=self.comp.JumpedCount=0;self.tick();self.first();self.second();self.assertEqual(self.lane.applied,2)
    def test_half(self):self.lane.rate=.5;self.start();self.first();self.second();self.assertEqual(self.vel.Z,400.)
    def test_neutral(self):self.lane.rate=1.;self.start();self.first();self.second();self.assertEqual(self.vel.Z,800.);self.assertEqual(self.lane.applied,0)
    def test_no_ground(self):self.ground=False;self.fall=True;self.start();self.first();self.second();self.assertEqual(self.vel.Z,800.)
    def test_no_first(self):self.start();self.ground=False;self.fall=True;self.second();self.assertEqual(self.vel.Z,800.)
    def test_stale(self):self.start();self.first();self.second(.2);self.assertEqual(self.vel.Z,800.)
    def test_gliding(self):self.start();self.first();self.comp.bIsGliding=True;self.second();self.assertEqual(self.vel.Z,800.)
    def test_controlled(self):self.start();self.first();self.controlled=True;self.second();self.assertEqual(self.vel.Z,800.)
    def test_join(self):self.start();self.first();self.ok=False;self.second();self.assertEqual(self.vel.Z,800.);self.assertIsNone(self.lane.record)
    def test_thread(self):self.start();self.first();self.tid=2;self.second();self.assertEqual(self.vel.Z,800.);self.assertIsNone(self.lane.record)
    def test_different_session(self):self.start();self.first();self.pc=Node();self.second();self.assertEqual(self.vel.Z,800.)
    def test_goal_disabled(self):self.start();self.first();self.goal.bUseInitialZVelocity=False;self.second();self.assertEqual(self.vel.Z,800.)
    def test_wrong_goal_velocity(self):self.start();self.first();self.goal.InitialZVelocity=1600.;self.second();self.assertEqual(self.vel.Z,800.)
    def test_late_goal_change(self):
        self.start();self.first();old=self.lane.context;calls=[0]
        def changed():
            calls[0]+=1
            if calls[0]==3:self.goal.GoalHeight=301.
            return old()
        self.lane.context=changed;self.second();self.assertEqual(self.vel.Z,800.)
    def test_stop_during_check(self):
        self.start();self.first();old=self.lane.context;calls=[0]
        def changed():
            calls[0]+=1
            if calls[0]==3:self.lane.stop('test')
            return old()
        self.lane.context=changed;self.second();self.assertEqual(self.vel.Z,800.)
    def test_invalid_rate(self):self.lane.rate=3.;self.assertFalse(self.lane.begin())
    def test_mismatched_counts(self):
        self.start();self.first();self.pawn.JumpCurrentCount=2;self.goal._name='JumpGoal_DoubleJump';self.tick();self.assertEqual(self.vel.Z,800.)
    def test_late_glide(self):
        self.start();self.first();old=self.lane.context;calls=[0]
        def changed():
            calls[0]+=1
            if calls[0]==3:self.comp.bIsGliding=True
            return old()
        self.lane.context=changed;self.second();self.assertEqual(self.vel.Z,800.)
    def test_readback_fault(self):
        class Bad(Node):
            def __setattr__(self,name,value):
                if name=='Z' and value>1000:raise RuntimeError('setter failed')
                super().__setattr__(name,value)
        self.vel=Bad(**vars(self.vel));self.comp.Velocity=self.vel
        self.start();self.first();self.second();self.assertTrue(self.lane.fault);self.assertIsNone(self.lane.record)
    def test_saved_options(self):
        m=self.base.m
        self.assertFalse(m.AUTOMATION_OPTIONS['double_jump'].value);self.assertEqual(m.DOUBLE_JUMP_RATE.value,1.)
        m.apply({'persistent_automation_double_jump':True,'double_jump_velocity_scale':1.5})
        self.assertTrue(m.AUTOMATION_OPTIONS['double_jump'].value);self.assertEqual(m.DOUBLE_JUMP_RATE.value,1.5)
        m.reset();self.assertFalse(m.AUTOMATION_OPTIONS['double_jump'].value);self.assertEqual(m.DOUBLE_JUMP_RATE.value,1.)
