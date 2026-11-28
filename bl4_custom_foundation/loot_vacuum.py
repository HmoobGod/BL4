"""Opt-in bounded relocation of existing pickups. No pickup RPC or inventory writes.
The live classifier and contact semantics are experimental, not gameplay certified.
"""
import math
from heapq import nsmallest
import re
import struct
from collections import Counter, deque
from itertools import product
from .gameplay_fields import identity
from .health_pulse import enum_name, select_flesh
from .weapon_rates import prop

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
# Indexes correspond to the observed two palettes above. This is a visual
# filter, not a native item rarity identity. Keep both category signals.
HIGH_GEAR_COLORS = (PALETTE[8][1], PALETTE[13][1])
# Exact inventory-definition body references; see SOURCES.md. The Eridium
# single stack uses a Lootables/Pile path, not a Pickups namespace.
ERIDIUM_SINGLE_STACK_BODY = '/Game/World/Interactives/Lootables/Pile/Eridium/SM_Eridium_Bar_Single.SM_Eridium_Bar_Single'
CASH_SINGLE_STACK_BODY = '/Game/World/Interactives/Pickups/Money/SM_Money_Stack_Single.SM_Money_Stack_Single'
# Exact decoded base inventory records; preserve legacy classification for
# other paths. These identify a body, not a native inventory identity.
AMMO_BODIES = frozenset('/Game/World/Interactives/Pickups/Ammo/SM_ammo_'+n+'.SM_ammo_'+n
                        for n in ('assault','pistol','shotgun','smg','sniper'))
HEALTH_PICKUP_BODY = '/Game/Pickups/Health/Body_Health_Pickup.Body_Health_Pickup'
EXACT_PICKUP_BODIES = {**dict.fromkeys(AMMO_BODIES,'ammo'), HEALTH_PICKUP_BODY:'health',
                       ERIDIUM_SINGLE_STACK_BODY:'eridium', CASH_SINGLE_STACK_BODY:'cash'}

# Only decoded standard bodies identify the corresponding reserve. Never infer
# reserve type from broad path tokens or the generic ammo beam.
AMMO_TYPES = {('/Game/World/Interactives/Pickups/Ammo/SM_ammo_'+n+'.SM_ammo_'+n): (key,enum)
              for n,key,enum in (('assault','assaultrifle','AssaultRifle'),('pistol','pistol','Pistol'),
                                 ('shotgun','shotgun','Shotgun'),('smg','smg','SMG'),('sniper','sniper','Sniper'))}


class AmmoNeedReader:
    """Read-only exact native ammo current/max resolver, never a setter."""
    def __init__(self,functions,bound,def_type,def_struct):
        from .native_resource_rates import LIB, DEF, SPECS
        self.def_type,self.def_struct=def_type,def_struct
        if def_struct._path_name()!=DEF:raise ValueError('ammo attribute definition type mismatch')
        name='GetValueOfAttribute';sig=SPECS[name];path=LIB+name
        fs=[f for f in functions if f._path_name()==path]
        if len(fs)!=1:raise ValueError('ammo getter missing or ambiguous')
        fn=fs[0];ps=tuple(fn._properties())
        if (fn.Outer._path_name()!=LIB[:-1] or fn.NumParams!=len(sig)
                or tuple((str(p.Name),type(p).__name__) for p in ps)!=sig
                or any(p.ArrayDim!=1 for p in ps)
                or ps[1].PropertyClass._path_name()!='/Script/CoreUObject.Object'):
            raise ValueError('ammo getter signature mismatch')
        self.get=bound(functions,path,sig)

    def definition(self,key,ammo_type,which):
        name='ammo_'+key+'_'+which.lower()+'value'
        d=self.def_type(name,self.def_struct,True)
        if type(d) is not self.def_type or d._name!=name or identity(d._type)!=identity(self.def_struct):
            raise ValueError('ammo definition identity mismatch')
        for member in ('Context','Value'):prop(d._type,member,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if (c._type._path_name()!='/Script/GbxEngine.ActorContextResolver'
                or v._type._path_name()!='/Script/OakGame.OakAmmoValueResolver'):
            raise ValueError('ammo resolver mismatch')
        for member,path in (('AmmoType','/Script/OakGame.EOakAmmoType'),('Value','/Script/OakGame.EOakAmmoResolverValue')):
            if prop(v._type,member,'ZEnumProperty').Enum._path_name()!=path:raise ValueError('ammo enum mismatch')
        prop(v._type,'bFromPickup','ZBoolProperty')
        if enum_name(v.AmmoType)!=ammo_type or enum_name(v.Value)!=which or v.bFromPickup is not False:
            raise ValueError('ammo reserve selector mismatch')
        return name,identity(d)

    def __call__(self,pawn,body):
        key,ammo_type=AMMO_TYPES[body]
        if pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name():
            raise ValueError('local character required')
        c,ci=self.definition(key,ammo_type,'Current');m,mi=self.definition(key,ammo_type,'Max')
        if ci==mi:raise ValueError('ammo definitions alias')
        current=self.get(c,pawn,-123456.);maximum=self.get(m,pawn,-123456.)
        if (type(current) not in (int,float) or type(maximum) not in (int,float)
                or not math.isfinite(current) or not math.isfinite(maximum)
                or not 0<=current<=maximum<=1e6 or maximum<=0
                or current!=int(current) or maximum!=int(maximum)):
            raise ValueError('ammo reserve readback unresolved')
        return current/maximum


def lazy_ammo_reader(sdk,bound):
    # Optional read-only compatibility enhancement; no binding scan until an
    # exact ammo candidate is encountered. Unsupported builds retain old path.
    reader=None;attempted=False
    def read(pawn,body):
        nonlocal reader,attempted
        if not attempted:
            attempted=True
            from .native_resource_rates import DEF
            defs=[d for d in sdk.find_all('ScriptStruct',exact=False) if d._path_name()==DEF]
            if len(defs)!=1:return None
            fs=[f for f in sdk.find_all('Function',exact=False) if str(f.Name)=='GetValueOfAttribute']
            reader=AmmoNeedReader(fs,bound,sdk.unreal.FGbxDefPtr,defs[0])
        return reader(pawn,body) if reader is not None else None
    return read


def flesh_need_reader(sdk):
    """Reuse the exact local living flesh layer, no native writes or calls."""
    def read(pawn):
        if pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name():
            raise ValueError('local character required')
        _,key,ratio=select_flesh(pawn,sdk.unreal.FGameDataHandle)
        return key,ratio
    return read


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
    if path in EXACT_PICKUP_BODIES:
        return EXACT_PICKUP_BODIES[path]
    if path.startswith('/Game/Gear/'):
        return 'gear'
    if words.intersection({'booster','shield','armor','shard'}):
        return None
    groups={'ammo':{'ammo','ammunition'},'cash':{'cash','money'},'eridium':{'eridium'},'health':{'health'}}
    matches={k for k,t in groups.items() if words.intersection(t)}
    # Positive pickup namespace, plus exactly one named category. Unknowns stay put.
    return next(iter(matches)) if len(matches)==1 and words.intersection({'pickup','pickups','consumable','consumables'}) else None


# The DLC namespace has an extra content-pack segment. Restrict new admission
# to concrete equipment families; require matching reflected body and package
# identities rather than accepting arbitrary DLC names or beam color alone.
DLC_GEAR_FAMILIES = frozenset(('Weapons', 'GrenadeGadgets', 'Gadgets',
                              'RepairKits', 'Enhancements', 'Shields', 'ClassMods'))
DLC_BODY_TYPE = '/Script/GbxGame.InventoryBodyData'


def is_dlc_gear_path(path):
    if type(path) is not str:return False
    segments=path.split('/')
    return len(segments)>4 and segments[:3]==['', 'Game', 'DLC'] and segments[4]=='Gear'


def dlc_gear_witness(actor, body=None):
    body = actor.BodyData if body is None else body
    path = body._path_name()
    if not is_dlc_gear_path(path):
        return None
    package, dot, object_name = path.rpartition('.')
    parts = package.split('/')
    # Exact package/object form, not arbitrary nested objects or generated assets.
    if (not dot or len(parts) < 7 or parts[:3] != ['', 'Game', 'DLC']
            or parts[4] != 'Gear' or parts[5] not in DLC_GEAR_FAMILIES
            or not all(re.fullmatch(r'[A-Za-z0-9_]+', x) for x in parts[3:])
            or object_name != parts[-1]
            or (parts[5]=='Gadgets' and (len(parts)<8 or parts[6]!='HeavyWeapons'))):
        raise ValueError('unsupported DLC gear namespace')
    if body_kind('/Game/' + '/'.join(parts[4:]) + '.' + object_name) != 'gear':
        raise ValueError('excluded DLC gear namespace')
    # Include the DLC pack name in the exclusions too.
    if body_kind('/Game/Gear/' + parts[3] + '/Body.Body') != 'gear':
        raise ValueError('excluded DLC pack namespace')
    descriptor = prop(actor.Class, 'BodyData', 'ZObjectProperty')
    if (descriptor.PropertyClass._path_name() != DLC_BODY_TYPE
            or body.Class._path_name() != DLC_BODY_TYPE
            or identity(descriptor.PropertyClass) != identity(body.Class)):
        raise ValueError('DLC body descriptor mismatch')
    outer = body.Outer
    if (outer is None or outer.Class._path_name() != '/Script/CoreUObject.Package'
            or outer._path_name() != package):
        raise ValueError('DLC body package mismatch')
    return (path, identity(body), identity(outer), identity(body.Class))


def pickup_body_witness(actor):
    """Keep the exact body object/path stable through dispatch.

    When reflection exposes BodyData, require its declared InventoryBodyData
    class and package identity. Legacy unavailable descriptors retain the
    original path/beam classifier, not a claim of native category identity.
    """
    body = actor.BodyData
    path = body._path_name()
    witness = (path, identity(body))
    properties = getattr(actor.Class, '_properties', None)
    if properties is None or not any(str(p.Name) == 'BodyData' for p in properties()):
        return witness
    descriptor = prop(actor.Class, 'BodyData', 'ZObjectProperty')
    cls = body.Class
    if (descriptor.PropertyClass._path_name() != DLC_BODY_TYPE
            or cls._path_name() != DLC_BODY_TYPE
            or identity(descriptor.PropertyClass) != identity(cls)):
        raise ValueError('pickup body descriptor mismatch')
    package, dot, name = path.rpartition('.')
    outer = body.Outer
    if (not dot or not name or name != package.rsplit('/', 1)[-1]
            or outer is None or outer.Class._path_name() != '/Script/CoreUObject.Package'
            or outer._path_name() != package):
        raise ValueError('pickup body package mismatch')
    return witness + (identity(cls), identity(outer))


def classify(actor, high_gear_only=False):
    body=actor.BodyData
    if body is None:
        return None  # material-only names are ambiguous
    path=body._path_name()
    if is_dlc_gear_path(path):
        try:
            if dlc_gear_witness(actor,body) is None:return None
        except Exception:return None
        k='gear'
    elif path == ERIDIUM_SINGLE_STACK_BODY:
        # Only this exact data-backed pile body is admitted. Require the full
        # reflected body/package witness, not the legacy name-only fallback.
        try:
            if len(pickup_body_witness(actor)) != 4:return None
        except Exception:return None
        k='eridium'
    else:k=body_kind(path)
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
    values=struct.unpack('<4f',data)
    if color_kind(values)!=k:return None
    if k=='gear' and high_gear_only and not any(max(abs(a-b) for a,b in zip(values,c))<=.00002 for c in HIGH_GEAR_COLORS):return None
    return k


def native_gear_identity(actor):
    """Read an existing reflected item instance ID, never decode opaque identity.

    Older/unexposed layouts retain actor-only admission. A present but malformed
    item descriptor is rejected. An ID of zero is not positive identity evidence.
    IDs may be recycled: collisions conservatively suppress relocation.
    """
    properties = getattr(actor.Class, '_properties', None)
    if properties is None:
        return None
    if not any(str(p.Name) == 'item' for p in properties()):
        return None

    def struct(owner, name, type_name):
        typ = getattr(owner, '_type', None) or owner.Class
        d = prop(typ, name, 'ZStructProperty')
        expected = '/Script/GbxGame.' + type_name
        value = getattr(owner, name)
        if (d.Struct._path_name() != expected or value._type._path_name() != expected
                or identity(d.Struct) != identity(value._type)):
            raise ValueError('native gear struct mismatch')
        return value

    item = struct(actor, 'item', 'GbxItem')
    data = struct(item, 'data', 'GbxItemData')
    state = struct(item, 'State', 'GbxItemState')
    prop(data._type, 'InstanceId', 'ZUInt32Property')
    prop(state._type, 'Quantity', 'ZUInt32Property')
    instance, quantity = data.InstanceId, state.Quantity
    if (type(instance) is not int or type(quantity) is not int
            or not 0 <= instance <= 0xffffffff or not 0 <= quantity <= 0xffffffff):
        raise ValueError('invalid native gear identity')
    if instance == 0:
        return None
    if quantity == 0:
        raise ValueError('empty native gear item')
    return instance, quantity


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


# Bounded local placement ledger: avoid stacking gear onto previous attempted
# destinations. This is not a terrain/occupancy or collision prediction.
_GEAR_OFFSETS = tuple((r*math.cos(i*math.tau/n),r*math.sin(i*math.tau/n))
                      for r,n in ((200,8),(350,12),(480,16)) for i in range(n))
_NEIGHBORS = tuple(product((-1,0,1),repeat=3))


def gear_cell(pos):
    return tuple(math.floor(x/100) for x in pos)


class Airborne(ValueError):
    pass


class Vacuum:
    """One lease, one attempt per object, no retry or automatic gear collection."""
    def __init__(self,context,weak,find,make,clock,thread,report,categories,radius,continuous=False,high_gear_only=False,ammo_reader=None,health_reader=None):
        self.context,self.weak,self.find,self.make=context,weak,find,make
        self.clock,self.thread,self.report=clock,thread,report
        self.categories=frozenset(categories);self.radius=radius;self.continuous=continuous
        if type(high_gear_only) is not bool:raise ValueError('invalid rarity filter')
        self.high_gear_only=high_gear_only;self.ammo_reader=ammo_reader;self.health_reader=health_reader
        self.recent=deque();self.total_attempts=0;self.gear_targets={}
        self.record=None;self.fault=False;self.busy=False;self.attempted=set();self.gear_ids=set();self.moved=0;self.next_due=0

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
            self.attempted.clear();self.gear_ids.clear();self.recent.clear();self.gear_targets.clear();self.total_attempts=0;self.moved=0;self.next_due=now+.5
        except Exception as exc:self.report('HOLD: vacuum '+str(exc)[:120]);return False
        self.report('EXPERIMENT: vacuum armed '+('until stopped in original session; ' if self.continuous else '30s; ')+', '.join(sorted(self.categories))+'; native pickup unverified');return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.report(f'STOP: vacuum {reason}; {self.moved} native relocation successes, not confirmed pickups; moved items not restored')

    def update_preferences(self,categories,radius,high_gear_only=None):
        """Committed persistent preferences only; preserve the original lease and ledger.
        Empty filters pause scanning, but not session validation.
        """
        if self.record is None or self.busy or self.fault or not self.continuous:return False
        if self.thread()!=self.record[2]:return False
        categories=frozenset(categories)
        if not categories<=CATEGORIES or type(radius) not in (float,int) or not math.isfinite(radius) or not 5<=radius<=100:
            raise ValueError('invalid vacuum preferences')
        if high_gear_only is not None and type(high_gear_only) is not bool:raise ValueError('invalid rarity filter')
        self.categories,self.radius=categories,radius
        if high_gear_only is not None:self.high_gear_only=high_gear_only
        return True

    def gear_position(self,origin,vendors):
        for dx,dy in _GEAR_OFFSETS:
            pos=(origin[0]+dx,origin[1]+dy,origin[2])
            cell=gear_cell(pos)
            if cell in self.gear_targets:continue
            if any(distance(pos,v)<=500**2 for v in vendors):continue
            if any((old:=self.gear_targets.get(tuple(c+d for c,d in zip(cell,offset)))) is not None
                   and distance(pos,old)<100**2 for offset in _NEIGHBORS):continue
            return pos
        return None

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
        kind=classify(a,self.high_gear_only)
        if kind not in self.categories:return None
        native = native_gear_identity(a) if kind == 'gear' else None
        if native is not None and native[0] in self.gear_ids:return None
        dlc = dlc_gear_witness(a) if kind == 'gear' else None
        return dist,key+(native,dlc,pickup_body_witness(a)),kind

    def ammo_need(self,pawn,body):
        if self.ammo_reader is None or body not in AMMO_TYPES:return None
        try:
            ratio=self.ammo_reader(pawn,body)
            return ratio if type(ratio) in (int,float) and math.isfinite(ratio) and 0<=ratio<=1 else None
        except Exception:return None

    def health_need(self,pawn):
        try:
            key,ratio=self.health_reader(pawn)
            if type(key) is tuple and len(key)==3 and type(ratio) in (int,float) and math.isfinite(ratio) and 0<ratio<1:
                return key,ratio
        except Exception:pass
        return None

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
            if not self.categories:return
            vendors=self.vendors(pc,lev)
            actors=self.find('InventoryPickup',exact=True)
            if len(actors)>1024:raise ValueError('pickup scan exceeds limit')
            candidates=[];ammo_ratios={};health_sample=None;health_checked=False;health_dispatched=False
            gear_space='gear' in self.categories and self.gear_position(origin,vendors[0]) is not None
            for a in actors:
                try:
                    result=self.inspect(a,lev,origin,vendors)
                    if result is not None and (result[2]!='gear' or gear_space):
                        ratio=None
                        if result[2]=='ammo':
                            body=result[1][4][0]
                            if body not in ammo_ratios:ammo_ratios[body]=self.ammo_need(pawn,body)
                            ratio=ammo_ratios[body]
                            if ratio==1:continue
                        if result[2]=='health' and self.health_reader is not None:
                            if not health_checked:
                                health_sample=self.health_need(pawn);health_checked=True
                            if health_sample is None:continue
                        candidates.append((result,self.weak(a),ratio))
                except Exception:continue
            # Two actors presenting the same positive item ID in one candidate
            # scan are ambiguous; relocate neither, rather than pick one.
            counts = Counter(result[1][2][0] for result, _, _ in candidates if result[1][2] is not None)
            candidates = [c for c in candidates if c[0][1][2] is None or counts[c[0][1][2][0]] == 1]
            if self.health_reader is not None:
                health=[c for c in candidates if c[0][2]=='health']
                if health:
                    candidates=[c for c in candidates if c[0][2]!='health']+[min(health,key=lambda c:c[0][0])]
            # Keep nearest-first except a modest preference (at most 2x in
            # squared-distance score) for positively identified depleted ammo.
            for result,ref,ratio in nsmallest(4,candidates,key=lambda c:c[0][0]*(1 if c[2] is None else .5+.5*c[2])):
                if self.record is not snapshot:return
                if self.continuous:
                    while self.recent and self.recent[0]<=self.clock()-30:self.recent.popleft()
                    if len(self.recent)>=24:return
                    if len(self.attempted)>=4096:self.stop('session identity limit reached');return
                elif not self.continuous and len(self.attempted)>=24:self.stop('attempt limit reached');return
                pc,pawn,key,_,origin=self.resolve();a=ref()
                if a is None:continue
                # Prepare destination first; native getters/struct construction may
                # synchronously change actor ownership, classification or vendor state.
                _,item_key,kind=result
                if kind=='health' and self.health_reader is not None and health_dispatched:continue
                if (identity(a)!=item_key[0] or a.Class._path_name()!=PICKUP or not active(a)
                        or level(a)!=key[-1] or a.HasAuthority() is not True or a.Owner is not None):continue
                rot=bound(a,'K2_GetActorRotation',ROTATION,ROT_SIG)()
                if kind=='gear':
                    xyz=self.gear_position(origin,self.vendors(pc,key[-1])[0])
                    if xyz is None:continue
                else:xyz=(origin[0],origin[1],origin[2]-40)
                target=self.make('Vector',X=xyz[0],Y=xyz[1],Z=xyz[2])
                if self.record is not snapshot:return
                pc,pawn,key,_,latest_origin=self.resolve()
                if distance(latest_origin,origin)>25**2:continue
                # Revalidate the original weak actor and all classification/vendor
                # checks after preparation, not only before it. No retry on dispatch.
                a=ref()
                if a is None:continue
                try:
                    latest_vendors=self.vendors(pc,key[-1])
                    fresh=self.inspect(a,key[-1],latest_origin,latest_vendors)
                    if kind=='gear' and any(distance(xyz,v)<=500**2 for v in latest_vendors[0]):continue
                except Exception:continue
                if fresh is None or fresh[1:]!=result[1:]:continue
                teleport=bound(a,'K2_TeleportTo',TELEPORT,TP_SIG)
                if kind=='ammo':
                    latest_ratio=self.ammo_need(pawn,item_key[4][0])
                    # Do not spend the attempt when a reserve is now full or
                    # a previously witnessed reserve becomes unreadable.
                    if latest_ratio==1 or (ratio is not None and latest_ratio is None):continue
                if kind=='health' and self.health_reader is not None:
                    latest_health=self.health_need(pawn)
                    if latest_health is None or latest_health[0]!=health_sample[0]:continue
                _,_,_,_,final_origin=self.resolve()
                if self.record is not snapshot:return
                if self.clock()>=snapshot[3] or self.thread()!=snapshot[2]:
                    self.stop('scope ended before relocation');return
                if distance(final_origin,origin)>25**2:continue
                # The final scope getter can synchronously change any pickup,
                # including its body, beam, lock, ownership or actor lifetime.
                # Recheck the original weak object and category for ALL lanes.
                try:
                    a = ref()
                    if a is None:continue
                    # A moving pickup can leave the configured radius or enter
                    # an already observed vendor zone during the last scope read.
                    final_pos=location(a)
                    final_dist=distance(final_pos,final_origin)
                    if (not 150**2<final_dist<=(100*self.radius)**2
                            or any(distance(final_pos,v)<=500**2 or distance(final_origin,v)<=500**2 for v in latest_vendors[0])):continue
                    if (identity(a)!=item_key[0] or a._path_name()!=item_key[1]
                            or a.Class._path_name()!=PICKUP or not active(a)
                            or level(a)!=key[-1] or a.HasAuthority() is not True or a.Owner is not None
                            or a.RootPrimitiveComponent is None
                            or identity(a.RootPrimitiveComponent.Outer)!=identity(a)
                            or a.UsableActorState.bInteractabilityLockedReplicated is not False
                            or kind not in self.categories or classify(a,self.high_gear_only)!=kind
                            or pickup_body_witness(a)!=item_key[4]):continue
                    if kind == 'gear':
                        native = native_gear_identity(a)
                        if native != item_key[2] or (native is not None and native[0] in self.gear_ids):continue
                        if dlc_gear_witness(a) != item_key[3]:continue
                except Exception:continue
                if self.record is not snapshot:return
                if self.clock()>=snapshot[3] or self.thread()!=snapshot[2]:
                    self.stop('scope ended during final pickup checks');return
                if kind == 'gear' and native is not None:self.gear_ids.add(native[0])
                if kind=='health' and self.health_reader is not None:
                    # Consume at most one health relocation per scan. Do not infer healing
                    # from teleport success; the next scan observes current health anew.
                    health_dispatched=True
                self.attempted.add(item_key[0]);self.recent.append(self.clock());self.total_attempts+=1
                if kind=='gear':self.gear_targets[gear_cell(xyz)]=xyz
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
