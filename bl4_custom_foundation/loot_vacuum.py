"""Opt-in bounded relocation of existing pickups. No pickup RPC or inventory writes.
The live classifier and contact semantics are experimental, not gameplay certified.
"""
import math
import re
import struct
from collections import deque
from .gameplay_fields import identity
from .health_pulse import enum_name

CATEGORIES = frozenset(('ammo', 'cash', 'eridium', 'health', 'gear'))
# Factual color observations from community loot metadata, not source code reuse.
PALETTE = (
    ('ammo', (.435,.435,.435,1.)), ('cash',(1.,1.,0.,1.)),
    ('eridium',(.5,0.,1.,1.)), ('health',(1.,0.,0.,1.)),
    ('gear',(.287441,.278894,.391573,1.)), ('gear',(.010330,.250158,.025187,1.)),
    ('gear',(.016807,.119538,.434154,1.)), ('gear',(.254152,.010330,.450786,1.)),
    ('gear',(1.,.229151,0.,1.)), ('gear',(.514918,.491021,.623961,1.)),
    ('gear',(.095307,.558341,.111932,1.)), ('gear',(.018500,.337164,.590619,1.)),
    ('gear',(.479320,.056128,.658375,1.)), ('gear',(.309469,1.,.644480,1.)),
)
PICKUP = '/Script/GbxGame.InventoryPickup'
TELEPORT = '/Script/Engine.Actor:K2_TeleportTo'
LOCATION = '/Script/Engine.Actor:K2_GetActorLocation'
ROTATION = '/Script/Engine.Actor:K2_GetActorRotation'


def color_kind(values):
    if len(values)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in values):
        return None
    matches={k for k, c in PALETTE if max(abs(a-b) for a,b in zip(values,c))<=.00002}
    return next(iter(matches)) if len(matches)==1 else None


def body_kind(path):
    # Tokenize rather than substring matching (e.g. a gun named HealthDamage).
    if not isinstance(path,str) or not path.startswith('/Game/') or 'Default__' in path:
        return None
    words=set(re.findall(r'[a-z]+',re.sub(r'([a-z])([A-Z])',r'\1 \2',path).lower()))
    if words.intersection({'mission','quest','objective','vendor','vending','display','shop','showcase','preview','rewardpreview','missionreward'}):
        return None
    if path.startswith('/Game/Gear/'):
        return 'gear'
    if words.intersection({'booster','shield','armor','shard'}):
        return None
    groups={'ammo':{'ammo','ammunition'},'cash':{'cash','money'},'eridium':{'eridium'},'health':{'health'}}
    matches={k for k,t in groups.items() if words.intersection(t)}
    # Positive pickup namespace, plus exactly one named category. Unknowns stay put.
    return next(iter(matches)) if len(matches)==1 and words.intersection({'pickup','pickups','consumable','consumables'}) else None


def classify(actor):
    body=actor.BodyData
    if body is None:
        return None  # material-only names are ambiguous
    k=body_kind(body._path_name())
    if k is None:return None
    effect=actor.AttractEffectComponent
    if effect is None:return None
    params=effect.OverrideParameters
    raw=params.ParameterData
    if not 16<=len(raw)<=65536 or len(params.SortedParameterOffsets)>256:return None
    entries=[p.Offset for p in params.SortedParameterOffsets if str(p.Name)=='User.Color']
    if len(entries)!=1 or type(entries[0]) is not int or not 0<=entries[0]<=len(raw)-16:return None
    data=bytes(raw[entries[0]:entries[0]+16])
    if len(data)!=16:return None
    return k if color_kind(struct.unpack('<4f',data))==k else None


def point(v):
    xyz=tuple(getattr(v,k) for k in ('X','Y','Z'))
    if not all(type(n) in (int,float) and math.isfinite(n) and abs(n)<1e9 for n in xyz):raise ValueError('invalid location')
    return xyz


def distance(a,b):return sum((x-y)**2 for x,y in zip(a,b,strict=True))


def level(actor):
    outer=actor.Outer
    if outer is None or outer.Class._path_name()!='/Script/Engine.Level':raise ValueError('actor level unavailable')
    return identity(outer)


def bound(actor,name,path,signature):
    f=getattr(actor,name);fn=f.func
    props=tuple(fn._properties())
    actual=tuple((str(p.Name),type(p).__name__,p.Struct._path_name() if type(p).__name__=='ZStructProperty' else '') for p in props)
    if fn._path_name()!=path or fn.NumParams!=len(signature) or actual!=signature or any(p.ArrayDim!=1 for p in props):raise ValueError('unsupported native '+name)
    return f


VECTOR='/Script/CoreUObject.Vector'; ROTATOR='/Script/CoreUObject.Rotator'
LOC_SIG=(('ReturnValue','ZStructProperty',VECTOR),)
ROT_SIG=(('ReturnValue','ZStructProperty',ROTATOR),)
TP_SIG=(('DestLocation','ZStructProperty',VECTOR),('DestRotation','ZStructProperty',ROTATOR),('ReturnValue','ZBoolProperty',''))


def location(actor):return point(bound(actor,'K2_GetActorLocation',LOCATION,LOC_SIG)())


def active(actor):
    return (actor is not None and 'Default__' not in actor._path_name() and actor.IsActorBeingDestroyed() is False and actor.bHidden is False)


class Airborne(ValueError):
    pass


class Vacuum:
    """One lease, one attempt per object, no retry or automatic gear collection."""
    def __init__(self,context,weak,find,make,clock,thread,report,categories,radius,continuous=False):
        self.context,self.weak,self.find,self.make=context,weak,find,make
        self.clock,self.thread,self.report=clock,thread,report
        self.categories=frozenset(categories);self.radius=radius;self.continuous=continuous
        self.recent=deque();self.total_attempts=0
        self.record=None;self.fault=False;self.busy=False;self.attempted=set();self.moved=0;self.next_due=0

    def resolve(self):
        pc,pawn,state,ok=self.context()
        if not ok or enum_name(pawn.HealthCondition)!='Healthy' or not active(pawn):raise ValueError('healthy solo player required')
        lev=level(pawn)
        objs=(pc,pawn,state);key=tuple(identity(o) for o in objs)+(lev,)
        if self.record is not None:
            refs,original,tid,end=self.record
            if key!=original or self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,key[:3],strict=True)):
                raise ValueError('original session changed')
        grounded=pawn.CharacterMovement.IsMovingOnGround()
        if grounded is False:raise Airborne('grounded player required')
        if grounded is not True:raise ValueError('ground state unknown')
        return pc,pawn,key,objs,location(pawn)

    def begin(self):
        if self.record is not None or self.fault or self.busy:return False
        try:
            if not self.categories or not self.categories<=CATEGORIES or type(self.radius) not in (float,int) or not math.isfinite(self.radius) or not 5<=self.radius<=100:raise ValueError('select categories and 5–100m radius')
            _,_,key,objs,_=self.resolve();now=self.clock()
            self.record=(tuple(self.weak(o) for o in objs),key,self.thread(),math.inf if self.continuous else now+30)
            self.attempted.clear();self.recent.clear();self.total_attempts=0;self.moved=0;self.next_due=now+.5
        except Exception as exc:self.report('HOLD: vacuum '+str(exc)[:120]);return False
        self.report('EXPERIMENT: vacuum armed '+('until stopped in original session; ' if self.continuous else '30s; ')+', '.join(sorted(self.categories))+'; native pickup unverified');return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.report(f'STOP: vacuum {reason}; {self.moved} native relocation successes, not confirmed pickups; moved items not restored')

    def vendors(self,pc,lev):
        out=[];display=set();machines=self.find('OakVendingMachine',exact=False)
        if len(machines)>256:raise ValueError('too many vending machines')
        for m in machines:
            if m is None or 'Default__' in m._path_name() or m.IsActorBeingDestroyed() is True:continue
            if level(m)!=lev:continue
            # Reject nearby displays even if only the item-of-day is exposed.
            out.append(location(m));item=m.GetIOTDForPlayer(pc)
            if item is not None:display.add(identity(item))
        return out,display

    def inspect(self,a,lev,origin,vendors):
        if a is None or identity(a) in self.attempted:return None
        if a.Class._path_name()!=PICKUP or not active(a) or level(a)!=lev or a.HasAuthority() is not True or a.Owner is not None:return None
        if a.RootPrimitiveComponent is None or identity(a.RootPrimitiveComponent.Outer)!=identity(a):return None
        if a.UsableActorState.bInteractabilityLockedReplicated is not False:return None
        token=identity(a);key=(token,a._path_name())
        if token in self.attempted or token in vendors[1]:return None
        pos=location(a);dist=distance(pos,origin)
        if dist<=150**2 or dist>(100*self.radius)**2:return None
        if any(distance(pos,v)<=500**2 or distance(origin,v)<=500**2 for v in vendors[0]):return None
        kind=classify(a)
        if kind not in self.categories:return None
        return dist,key,kind

    def tick(self,permitted):
        if self.record is None or self.busy:return
        now=self.clock();snapshot=self.record
        if not permitted or self.thread()!=snapshot[2] or now>=snapshot[3]:self.stop('permission/thread/lifetime ended');return
        if now<self.next_due:return
        self.next_due=now+.5;self.busy=True
        try:
            pc,pawn,key,_,origin=self.resolve();lev=key[-1]
            if self.continuous:
                while self.recent and self.recent[0]<=now-30:self.recent.popleft()
                if len(self.recent)>=24:return
            vendors=self.vendors(pc,lev)
            actors=self.find('InventoryPickup',exact=True)
            if len(actors)>1024:raise ValueError('pickup scan exceeds limit')
            candidates=[]
            for a in actors:
                try:
                    result=self.inspect(a,lev,origin,vendors)
                    if result is not None:candidates.append((result,self.weak(a)))
                except Exception:continue
            for result,ref in sorted(candidates,key=lambda c:c[0][0])[:4]:
                if self.record is not snapshot:return
                if self.continuous:
                    while self.recent and self.recent[0]<=self.clock()-30:self.recent.popleft()
                    if len(self.recent)>=24:return
                    if len(self.attempted)>=4096:self.stop('session identity limit reached');return
                elif not self.continuous and len(self.attempted)>=24:self.stop('attempt limit reached');return
                pc,pawn,key,_,origin=self.resolve();a=ref()
                if a is None:continue
                # Revalidate identity, type, distance and vendor status just before dispatch.
                try: fresh=self.inspect(a,key[-1],origin,self.vendors(pc,key[-1]))
                except Exception:continue
                if fresh is None or fresh[1:]!=result[1:]:continue
                _,item_key,kind=fresh
                teleport=bound(a,'K2_TeleportTo',TELEPORT,TP_SIG)
                rot=bound(a,'K2_GetActorRotation',ROTATION,ROT_SIG)()
                if kind=='gear':
                    angle=(len(self.attempted)%8)*math.tau/8
                    xyz=(origin[0]+200*math.cos(angle),origin[1]+200*math.sin(angle),origin[2])
                else:xyz=(origin[0],origin[1],origin[2]-40)
                target=self.make('Vector',X=xyz[0],Y=xyz[1],Z=xyz[2])
                # Mark before native dispatch, even if it refuses. Never replay an overlap/RPC.
                if self.record is not snapshot or self.clock()>=snapshot[3] or self.thread()!=snapshot[2]:
                    self.stop('scope ended before relocation');return
                _,_,_,_,latest_origin=self.resolve()
                if self.record is not snapshot:return
                if distance(latest_origin,origin)>25**2:continue
                self.attempted.add(item_key[0]);self.recent.append(self.clock());self.total_attempts+=1
                try: moved=teleport(target,rot)
                except Exception as exc:
                    self.fault=True;self.stop('uncertain native relocation: '+str(exc)[:80]);return
                if moved is True:self.moved+=1
                elif moved is not False:self.fault=True;self.stop('unexpected native result');return
            if not self.continuous and len(self.attempted)>=24:self.stop('attempt limit reached')
        except Airborne:
            if not self.continuous:self.stop("grounded player required")
        except Exception as exc:self.stop(str(exc)[:120])
        finally:self.busy=False
