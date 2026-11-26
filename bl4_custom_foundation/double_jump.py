"""Experimental one-shot local second-jump vertical velocity scaling.
No shared goal edits, input injection, jump creation, or save changes.
The native height solver may override this field; actual height is unverified.
"""
import math
from .gameplay_fields import identity, slide_component
from .weapon_rates import prop
from .loot_vacuum import active, level, bound, point, VECTOR
from .health_pulse import enum_name

GOAL_TYPE = '/Script/GbxGame.JumpGoalDef'
FIRST = frozenset(('jumpgoal_default', 'jumpgoal_sprint'))
SECOND = 'jumpgoal_doublejump'
BOOL_RETURN = (('ReturnValue','ZBoolProperty',''),)


def struct(owner, name, path):
    d = prop(getattr(owner, '_type', None) or owner.Class, name, 'ZStructProperty')
    v = getattr(owner, name)
    if d.Struct._path_name() != path or v._type._path_name() != path or identity(d.Struct) != identity(v._type):
        raise ValueError('unexpected '+name+' struct')
    return v


def predicate(owner, name, path):
    value = bound(owner, name, path+':'+name, BOOL_RETURN)()
    if type(value) is not bool:
        raise ValueError('unexpected '+name+' result')
    return value


def observe(pawn, comp):
    prop(pawn.Class, 'JumpCurrentCount', 'ZIntProperty')
    prop(comp.Class, 'JumpedCount', 'ZIntProperty')
    count, native = pawn.JumpCurrentCount, comp.JumpedCount
    if type(count) is not int or type(native) is not int or not 0 <= count <= 16 or not 0 <= native <= 16:
        raise ValueError('invalid jump counts')
    nav = '/Script/Engine.NavMovementComponent'
    ground = predicate(comp,'IsMovingOnGround',nav)
    fall = predicate(comp,'IsFalling',nav)
    controlled = predicate(comp,'IsPerformingControlledMove','/Script/GbxGame.GbxCharacterMovementComponent')
    prop(comp.Class, 'bIsGliding', 'ZBoolProperty')
    gliding = comp.bIsGliding
    if type(gliding) is not bool:
        raise ValueError('glide state unknown')
    if ground and not fall and count == native == 0 and not controlled and not gliding:
        return ('ground', None, None, None), None
    if ground or not fall or controlled or gliding or count != native or count not in (1,2):
        return ('other', None, None, None), None
    details = struct(comp,'CurrentJump','/Script/GbxGame.JumpDetails')
    d = prop(details._type,'JumpGoal','ZGbxDefPtrProperty')
    goal = details.JumpGoal
    if (type(goal).__name__ != 'FGbxDefPtr' or d.Struct._path_name()!=GOAL_TYPE
            or goal._type._path_name()!=GOAL_TYPE or identity(d.Struct)!=identity(goal._type)):
        raise ValueError('unexpected current jump goal')
    name = str(goal._name).casefold()
    if count == 1:
        return ('first' if name in FIRST else 'other', None, None, None), None
    if name != SECOND:
        return ('other', None, None, None), None
    prop(goal._type,'bUseInitialZVelocity','ZBoolProperty')
    prop(goal._type,'InitialZVelocity','ZFloatProperty')
    prop(goal._type,'GoalHeight','ZFloatProperty')
    initial, height = goal.InitialZVelocity, goal.GoalHeight
    if (goal.bUseInitialZVelocity is not True or type(initial) not in (int,float)
            or type(height) not in (int,float) or not math.isfinite(initial) or not math.isfinite(height)
            or not 100 <= initial <= 2500 or not 0 < height <= 3000):
        return ('other',None,None,None),None
    velocity=struct(comp,'Velocity',VECTOR)
    for k in ('X','Y','Z'): prop(velocity._type,k,'ZDoubleProperty')
    xyz=point(velocity)
    if not .75*initial <= xyz[2] <= 1.25*initial:
        return ('other',None,None,None),None
    return ('second', (identity(goal),float(initial),float(height)), identity(velocity), xyz), velocity


class DoubleJump:
    def __init__(self,context,weak,clock,thread,report,rate):
        self.context,self.weak,self.clock,self.thread,self.report=context,weak,clock,thread,report
        self.rate=rate;self.record=None;self.fault=False;self.busy=False
        self.phase='wait';self.last_first=0.;self.next_due=0.;self.applied=0

    def resolve(self):
        pc,pawn,state,ok=self.context()
        if not ok or not active(pawn) or enum_name(pawn.HealthCondition)!='Healthy':
            raise ValueError('healthy solo player required')
        comp=slide_component(pawn)
        objs=(pc,pawn,state,comp); key=tuple(identity(o) for o in objs)+(level(pawn),)
        if self.record is not None:
            refs,original,tid=self.record
            if key!=original or self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,key[:4],strict=True)):
                raise ValueError('original jump session changed')
        return objs,key

    def begin(self):
        if self.record is not None or self.fault or self.busy:return False
        try:
            if type(self.rate) not in (int,float) or not math.isfinite(self.rate) or not .5<=self.rate<=2.:
                raise ValueError('invalid second-jump scale')
            objs,key=self.resolve()
            self.record=(tuple(self.weak(o) for o in objs),key,self.thread())
            self.phase='wait';self.next_due=self.clock();self.applied=0
        except Exception as exc:
            self.report('HOLD: double jump '+str(exc)[:100]);return False
        self.report('EXPERIMENT: second-jump velocity armed; observe ground, then two distinct jumps. Height unverified.')
        return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.phase='wait'
            self.report(f'STOP: double jump {reason}; {self.applied} velocity changes; completed impulses not reversed')

    def tick(self,permitted,event_pawn=None):
        if self.record is None or self.fault or self.busy:return
        snapshot=self.record;now=self.clock()
        if not permitted or self.thread()!=snapshot[2]:self.stop('permission/thread ended');return
        event = event_pawn is not None
        if event:
            # Ignore other characters and stale wrappers before any native inspection.
            try:
                original = snapshot[0][1]()
                if original is None or identity(original)!=snapshot[1][1] or identity(event_pawn)!=snapshot[1][1]:return
            except Exception:return
        elif now<self.next_due:return
        if not event:self.next_due=now+.05
        self.busy=True;dispatched=False
        try:
            objs,key=self.resolve();sample,velocity=observe(objs[1],objs[3]);phase=sample[0]
            if self.record is not snapshot:return
            # Native event may precede coherent movement/count update. Leave the
            # periodic fallback and sequence untouched in that case.
            if event and phase not in ('first','second'):return
            if phase=='ground':self.phase='ready';return
            if phase=='first' and self.phase in ('ready','first'):
                self.phase='first';self.last_first=now;return
            if event and (phase!='second' or self.phase!='first'):return
            previous=self.phase;self.phase='used'
            if phase!='second' or previous!='first' or not 0<=now-self.last_first<=.125 or self.rate==1.:return
            z=sample[3][2];target=z*self.rate
            if not 0<target<=2500:return
            fresh,freshkey=self.resolve()
            confirm,live=observe(fresh[1],fresh[3])
            if self.record is not snapshot or freshkey!=key or confirm!=sample or self.thread()!=snapshot[2]:return
            # Recheck final original scope after native predicates. No catch-up.
            final,finalkey=self.resolve()
            if self.record is not snapshot or finalkey!=key or identity(final[3])!=identity(fresh[3]):return
            if (identity(final[3].Velocity)!=sample[2] or point(final[3].Velocity)!=sample[3]
                    or final[1].JumpCurrentCount!=2 or final[3].JumpedCount!=2
                    or identity(final[3].CurrentJump.JumpGoal)!=sample[1][0]
                    or str(final[3].CurrentJump.JumpGoal._name).casefold()!=SECOND
                    or final[3].CurrentJump.JumpGoal.InitialZVelocity!=sample[1][1]
                    or final[3].CurrentJump.JumpGoal.GoalHeight!=sample[1][2]
                    or final[3].CurrentJump.JumpGoal.bUseInitialZVelocity is not True
                    or final[3].bIsGliding is not False or identity(live)!=sample[2]
                    or self.record is not snapshot or self.thread()!=snapshot[2]):return
            dispatched=True
            live.Z=target
            observed=point(final[3].Velocity)
            if observed[:2]!=sample[3][:2] or not math.isclose(observed[2],target,rel_tol=1e-7,abs_tol=1e-6):
                raise ValueError('velocity readback mismatch')
            self.applied+=1
            self.report('EXPERIMENT: local second-jump vertical velocity changed; height unverified')
        except Exception as exc:
            if dispatched:self.fault=True;self.report('FAULT: second-jump velocity write/readback uncertain; exit game')
            self.stop(str(exc)[:100])
        finally:self.busy=False
