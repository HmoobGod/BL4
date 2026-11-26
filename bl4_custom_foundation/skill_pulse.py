"""Experimental bounded action-skill assist. Read definitions only; never edit them."""
import math
from .gameplay_fields import identity
from .weapon_rates import prop
from .health_pulse import numeric, enum_name

PATH='/Script/GbxGame.GbxSkillComponentFunctions_ResourcePool:'
REF='/Script/GbxGame.GbxSkillComponentReference'
ACTION='/Script/OakGame.GbxSkillComponentFunctions_ActionSkill:'
ACTION_NAMES=tuple('Get'+mode+'AsPercent'+suffix for mode in ('Cooldown','Duration') for suffix in ('','Internal'))
SPECS={n:(('ComponentReference','ZStructProperty'),('ResourcePool','ZGameDataHandleProperty'),('ReturnValue','ZFloatProperty')) for n in ('GetCurrentPercentage','GetCurrentValue','GetMaxValue')}
SPECS['RefillPercentage']=(('ComponentReference','ZStructProperty'),('ResourcePool','ZGameDataHandleProperty'),('Percentage','ZFloatProperty'),('MaxPercentage','ZFloatProperty'))

def bind(functions, existing):
    out=[]; ref_type=None
    for name,sig in SPECS.items():
        matches=[f for f in functions if f._path_name()==PATH+name]
        if len(matches)!=1: raise ValueError('skill pool function missing or ambiguous')
        fn=matches[0]; ps=tuple(fn._properties())
        if not ps or any(p.ArrayDim!=1 for p in ps) or ps[0].Struct._path_name()!=REF or fn.Outer._path_name()!=PATH[:-1]:
            raise ValueError('skill pool signature mismatch')
        if ref_type is not None and identity(ref_type)!=identity(ps[0].Struct): raise ValueError('reference type changed')
        ref_type=ps[0].Struct
        out.append(existing(functions,PATH+name,sig))
    prop(ref_type,'Context','ZObjectProperty')
    if prop(ref_type,'Context','ZObjectProperty').PropertyClass._path_name()!='/Script/GbxGame.GbxSkillScript': raise ValueError('reference context mismatch')
    if prop(ref_type,'ComponentID','ZStructProperty').Struct._path_name()!='/Script/CoreUObject.Guid': raise ValueError('reference GUID mismatch')
    return ref_type,tuple(out)

def bind_action_percent(functions, existing, mode, ref_type):
    """Independent native action-skill getters, not an inferred rate setter."""
    if mode not in ('cooldown','duration'): raise ValueError('unknown adaptive skill mode')
    out=[]
    for internal in (False,True):
        name='Get'+mode.title()+'AsPercent'+('Internal' if internal else '')
        path=ACTION+name
        matches=[f for f in functions if f._path_name()==path]
        if len(matches)!=1: raise ValueError('action skill percent getter unavailable')
        fn=matches[0]; ps=tuple(fn._properties())
        sig=(('ComponentReference','ZStructProperty') if internal else ('target','ZObjectProperty'),('ReturnValue','ZFloatProperty'))
        if len(ps)!=2 or any(p.ArrayDim!=1 for p in ps) or fn.Outer._path_name()!=ACTION[:-1]:
            raise ValueError('action skill getter descriptor mismatch')
        if internal:
            if ps[0].Struct._path_name()!=REF or identity(ps[0].Struct)!=identity(ref_type): raise ValueError('action skill reference mismatch')
        elif ps[0].PropertyClass._path_name()!='/Script/OakGame.OakCharacter':
            raise ValueError('action skill target mismatch')
        out.append(existing(functions,path,sig))
    return tuple(out)

NATIVE_REFILL_NAMES=('RefillCooldownInternal','RefillDurationInternal')
# Independently implemented named main-cooldown path. These are factual game
# resource identifiers reported in the Save Editor 1.0.19 resource table notes;
# executable/secondary/charge resources are deliberately not in this allowlist.
MAIN_COOLDOWNS=frozenset(n.casefold() for n in (
    'Resource_DarkSiren_ActionSkill_PhaseAvatar_Cooldown',
    'Resource_DarkSiren_ActionSkill_PhaseFamiliar_Cooldown',
    'Resource_DarkSiren_ActionSkill_PhaseShard_Cooldown',
    'Resource_Corpohacker_ActionSkill_Contagion_Cooldown',
    'Resource_Corpohacker_ActionSkill_Manifestation_Cooldown',
    'Resource_Corpohacker_ActionSkill_VPN_Cooldown',
    'Resource_Paladin_ActionSkill_Scourge_Cooldown',
    'Resource_Paladin_ActionSkill_Warforge_Cooldown',
    'Resource_Paladin_ActionSkill_WeaponMaster_Cooldown',
    'resource_exo_autolock_cooldown', 'Resource_Exo_BunkerBuster_cooldown',
    'Resource_Exo_BunkerBuster3_Cooldown', 'resource_exo_heavyarms_cooldown',
    'resource_grav_exodus_cooldown', 'resource_grav_stasis_cooldown',
    'Resource_Grav_Terminal2_Cooldown', 'Resource_Robo_Cleromancy_Cooldown',
    'Resource_Robo_SleightOfHand_Cooldown', 'Resource_Robo_Crossfire_Cooldown',
))
DIRECT='/Script/GbxGame.GameResourcePoolFunctionLibrary:'
DIRECT_NAMES=('GetResourcePoolValue','GetResourcePoolPercent','AdjustResourcePoolValue')
DIRECT_INTERFACE='/Script/GbxGame.GameResourcePoolOwnerInterface'


def bind_direct_cooldown(functions, existing):
    """Exact reflected pawn resource functions; no constructed/guessed handle."""
    out=[]; kind=None
    for name in DIRECT_NAMES:
        matches=[f for f in functions if f._path_name()==DIRECT+name]
        if len(matches)!=1:raise ValueError('named cooldown API unavailable')
        f=matches[0];ps=tuple(f._properties())
        sig=(('owner','ZInterfaceProperty'),('InResource','ZGameDataHandleProperty'),
             ('InValue' if name==DIRECT_NAMES[-1] else 'ReturnValue','ZFloatProperty'))
        if (len(ps)!=3 or any(p.ArrayDim!=1 for p in ps) or f.Outer._path_name()!=DIRECT[:-1]
                or tuple((str(p.Name),type(p).__name__) for p in ps)!=sig
                or ps[0].InterfaceClass._path_name()!=DIRECT_INTERFACE):
            raise ValueError('named cooldown signature/interface mismatch')
        t=ps[1].TypeHandle
        if type(t) is not int or not 0<t<=0xffffffff or (kind is not None and kind!=t):
            raise ValueError('named cooldown resource type mismatch')
        kind=t;out.append(existing(functions,DIRECT+name,sig))
    return (*out,kind)


def direct_sample(api,pawn,h,ht):
    name,kind,_=handle(h,ht)
    if kind!=api[3]:raise ValueError('named cooldown resource type changed')
    cur=numeric(api[0](pawn,h));p=numeric(api[1](pawn,h))
    if not 0<=cur<=1e9 or not 0<=p<=1 or (p==0)!=(cur==0):
        raise ValueError('named resource readback invalid')
    return cur,p

REFILL_ENUM='/Script/OakGame.EOakActionSkillResourceRefillMode'
# Factual event identifiers observed in the supplied Cross-Fire reference.
CROSSFIRE_CLASS='/Game/DLC/Cowbell/PlayerCharacters/RoboDealer/ActionSkills/CrossFire/Scripts/SkillScript_Robo_Crossfire.SkillScript_Robo_Crossfire_C'
CROSSFIRE_EVENTS=('K2Node_GbxSkillStateEvent_Enabled_5_S_General_Active_Enabled',
                  'K2Node_GbxSkillStateEvent_Enabled_7_S_General_Ending_Enabled')

def bind_native_refill(functions, existing, mode, ref_type):
    """Dedicated component-scoped action-skill API; never call pawn and controller together."""
    if mode not in ('cooldown','duration'):raise ValueError('unknown skill refill mode')
    path=ACTION+'Refill'+mode.title()+'Internal'
    matches=[f for f in functions if f._path_name()==path]
    if len(matches)!=1:raise ValueError('native action skill refill unavailable')
    fn=matches[0];ps=tuple(fn._properties())
    sig=(('ComponentReference','ZStructProperty'),('Percent','ZFloatProperty'),('RefillMode','ZEnumProperty'))
    if (len(ps)!=3 or any(p.ArrayDim!=1 for p in ps) or fn.Outer._path_name()!=ACTION[:-1]
            or identity(ps[0].Struct)!=identity(ref_type) or ps[0].Struct._path_name()!=REF
            or ps[2].Enum._path_name()!=REFILL_ENUM):raise ValueError('native skill refill descriptor mismatch')
    return existing(functions,path,sig)

def guid(g):
    if g._type._path_name()!='/Script/CoreUObject.Guid': raise ValueError('GUID type mismatch')
    v=tuple(getattr(g,k) for k in ('A','B','C','D'))
    if any(type(x) is not int or not -2**31<=x<2**32 for x in v): raise ValueError('invalid GUID')
    return v

def handle(h,ht):
    if type(h) is not ht or type(h._name) is not str or not h._name or h._name=='None' or type(h._type_handle) is not int or not 0<h._type_handle<=0xffffffff: raise ValueError('unresolved resource handle')
    return h._name,h._type_handle,identity(h)

def has_type(t,path):
    return any(x._path_name()==path for x in (t,*t._superfields()))

SET_CLASS='/Script/GbxGame.GbxSkillComponentSetData'
SET_ENTRY='/Script/GbxGame.GbxSkillDataComponent'


def loaded_set_entries(cls, soft_identifier):
    """Read only already-resolved soft references; never load an asset."""
    arr=cls.SkillComponentSets
    if not len(arr):return [],()
    if not callable(soft_identifier) or len(arr)>32:raise ValueError('external component sets unsupported')
    inner=prop(cls,'SkillComponentSets','ZArrayProperty').Inner
    if type(inner).__name__!='ZSoftObjectProperty' or inner.PropertyClass._path_name()!=SET_CLASS:
        raise ValueError('external set descriptor mismatch')
    entries=[];keys=[];paths=set();ids=set()
    for i in range(len(arr)):
        path=soft_identifier(arr,i)
        obj=arr[i]
        if type(path) is not str or not path.startswith('/Game/') or obj is None or obj._path_name()!=path or 'Default__' in path:
            raise ValueError('external set not resolved to exact asset')
        if obj.Class._path_name()!=SET_CLASS:raise ValueError('external set class mismatch')
        token=identity(obj)
        if path in paths or token in ids:raise ValueError('duplicate external set')
        paths.add(path);ids.add(token)
        element=prop(obj.Class,'Components','ZArrayProperty').Inner
        if type(element).__name__!='ZStructProperty' or element.Struct._path_name()!=SET_ENTRY:
            raise ValueError('external component entry descriptor mismatch')
        components=obj.Components
        if len(components)>128 or len(entries)+len(components)>128:raise ValueError('component count excessive')
        for e in components:
            if identity(e._type)!=identity(element.Struct):raise ValueError('external component entry type mismatch')
            entries.append(((identity(cls),path,token),e))
        keys.append((path,token))
    return entries,tuple(keys)


def candidates(skill,pawn,ht,inline,soft_identifier=None,named_type=None):
    if 'Default__' in skill._path_name() or identity(skill.SkillOwner)!=identity(pawn): raise ValueError('foreign skill')
    scripts=skill.SkillScripts
    if not 0<len(scripts)<=32: raise ValueError('skill scripts unavailable')
    out=[]
    for s in scripts:
        if 'Default__' in s._path_name() or identity(s.Skill)!=identity(skill) or identity(s.Actor)!=identity(pawn) or s.bIsInitialized is not True: raise ValueError('skill script owner/init mismatch')
        if not has_type(s.Class,'/Script/GbxGame.GbxSkillScript'): raise ValueError('script type mismatch')
        # Inline and already-resolved external definitions are read-only.
        # Every origin is pinned; no forced asset load or guessed reference.
        cls=s.Class
        chain=(cls,*cls._superfields())
        if len(chain)>32 or len({identity(c) for c in chain})!=len(chain):
            raise ValueError('skill class chain ambiguous')
        entries=[];layout=[];external_paths=set();external_ids=set()
        for c in chain:
            if not hasattr(c,'SkillComponents'):
                if c is cls:raise ValueError('component definitions unavailable')
                continue
            if len(c.SkillComponents)>128:raise ValueError('component count excessive')
            entries.extend(((identity(c),),e) for e in c.SkillComponents)
            external,keys=loaded_set_entries(c,soft_identifier)
            for path,token in keys:
                if path in external_paths or token in external_ids:raise ValueError('duplicate external set in class chain')
                external_paths.add(path);external_ids.add(token)
            layout.append((identity(c),keys))
            entries.extend(external)
            if len(entries)>128:raise ValueError('component count excessive')
        seen=set()
        for origin,e in entries:
            d=e.ComponentData
            if type(d) is not inline: raise ValueError('inline component wrapper unavailable')
            if not has_type(d._type,'/Script/GbxGame.GbxSkillComponentData'): raise ValueError('component data type unavailable')
            cid=guid(d.ComponentID)
            if cid in seen or not any(cid): raise ValueError('duplicate or missing component ID')
            seen.add(cid)
            if not has_type(d._type,'/Script/OakGame.GbxSkillComponentData_ActionSkill'): continue
            charge=guid(d.ChargeComponentID);aux=d.AuxCooldownPoolDefs
            if (any(charge) or len(aux)) and named_type is None:raise ValueError('charge/auxiliary skill unsupported')
            definitions=(d.CooldownPoolDef,d.DurationPoolDef)
            keys=tuple(handle(h,ht) for h in definitions)
            resources=tuple(h.resource for h in definitions)
            rk=tuple(handle(h,ht) for h in resources)
            if len({k[:2] for k in keys+rk})!=4 or len({k[2] for k in keys+rk})!=4: raise ValueError('ambiguous skill pool identity')
            peers=();extra=()
            if any(charge) or len(aux):
                if rk[0][0].casefold() not in MAIN_COOLDOWNS or rk[0][1]!=named_type:
                    raise ValueError('named main cooldown not positively identified')
                if len(aux)>8:raise ValueError('auxiliary cooldown count excessive')
                auxdefs=tuple(aux);auxresources=tuple(h.resource for h in auxdefs)
                auxkeys=tuple(handle(h,ht) for h in auxdefs+auxresources)
                peers=auxresources;chargekeys=()
                if any(charge):
                    matched=[e.ComponentData for _,e in entries if guid(e.ComponentData.ComponentID)==charge]
                    if (len(matched)!=1 or charge==cid or
                            matched[0]._type._path_name()!='/Script/OakGame.GbxSkillComponentData_Charges'):
                        raise ValueError('distinct charge component unavailable')
                    ch=matched[0].ChargePoolHandle;ck=handle(ch,ht)
                    # Accept an explicitly resolved resource or a definition
                    # with a resolved resource of the native reader's type.
                    if ck[1]==named_type:
                        chres=ch;chargekeys=(ck,)
                    elif ck[1]==keys[0][1]:
                        chres=ch.resource;chargekeys=(ck,handle(chres,ht))
                    else:raise ValueError('charge pool type unavailable')
                    peers=peers+(chres,)
                allkeys=keys+rk+auxkeys+chargekeys
                if (any(handle(h,ht)[1]!=named_type for h in peers)
                        or len({(k[0].casefold(),k[1]) for k in allkeys})!=len(allkeys)
                        or len({k[2] for k in allkeys})!=len(allkeys)):
                    raise ValueError('main, duration, auxiliary or charge pool alias')
                extra=(charge,auxkeys,chargekeys)
            out.append((s,d.ComponentID,cid,resources,keys+rk,(origin,tuple(layout),extra),peers))
    return out

class SkillPulse:
    def __init__(self,context,weak,ht,inline,construct,ref_type,api,find,clock,thread,report,mode,continuous=False,adaptive_api=None,rate=2.,soft_identifier=None,follow=False,native_refill=None,event_class=None,direct_api=None):
        if mode not in ('cooldown','duration'): raise ValueError('unknown skill mode')
        self.context,self.weak,self.ht,self.inline,self.construct,self.ref_type,self.api,self.find=context,weak,ht,inline,construct,ref_type,api,find
        self.clock,self.thread,self.report,self.mode=clock,thread,report,mode
        self.continuous=continuous is True
        self.follow=self.continuous and follow is True
        self.soft_identifier=soft_identifier
        self.record=None;self.fault=False;self.busy=False;self.prev=None;self.pending=None;self.rises=0;self.follow_candidate=None
        if adaptive_api is not None and (not self.continuous or len(adaptive_api)!=2): raise ValueError('adaptive mode requires continuous and two getters')
        if native_refill is not None and (adaptive_api is None or not callable(native_refill)):raise ValueError('native refill requires adaptive cross-checks')
        self.native_refill=native_refill
        if direct_api is not None and (mode!='cooldown' or native_refill is None or self.follow or len(direct_api)!=4):
            raise ValueError('named main cooldown requires dedicated adaptive cooldown, follow OFF')
        self.direct_api=direct_api;self.named_max=None
        if event_class is not None and (mode!='duration' or native_refill is None or self.follow):
            raise ValueError('Cross-Fire lifecycle requires dedicated adaptive duration and follow OFF')
        self.event_class=event_class;self.event_active=False;self.event_epoch=0
        self.adaptive_api=adaptive_api;self.rate=2.;self.sample_at=None;self.last_delta=None
        self.update_adaptive_rate(rate)
    def observe_event(self,script,starting):
        # Observation only. Never dispatch from an event hook. An ending event
        # must invalidate even if it occurs reentrantly inside a pool getter.
        if self.event_class is None or self.record is None:return
        refs,ids,tid,_,_,_=self.record
        if (self.thread()!=tid or refs[4]() is None or identity(refs[4]())!=ids[4]
                or identity(script)!=ids[4] or script.Class._path_name()!=CROSSFIRE_CLASS
                or identity(script.Class)!=self.event_class):return
        self.event_epoch+=1
        self.event_active=starting is True and not self.busy
        self.prev=None;self.sample_at=None;self.rises=0;self.last_delta=None;self.pending=None

    def update_adaptive_rate(self,rate):
        if type(rate) not in (int,float) or not math.isfinite(rate) or not 1.<=rate<=3.: raise ValueError('adaptive skill rate out of range')
        if rate!=self.rate:
            self.rate=rate;self.rises=0;self.last_delta=None;self.sample_at=None
    def owned_skills(self,pawn):
        skills=self.find()
        if len(skills)>256: raise ValueError('skill search exceeds bound')
        return [s for s in skills if s.SkillOwner is not None and identity(s.SkillOwner)==identity(pawn)]
    def scope(self,snapshot):
        refs,ids,tid,end,_,_=snapshot
        pc,pawn,state,ok=self.context()
        if (not ok or self.thread()!=tid or self.clock()>=end or enum_name(pawn.HealthCondition)!='Healthy'
                or tuple(identity(x) for x in (pc,pawn,state))!=ids[:3]
                or any(r() is None or identity(r())!=i for r,i in zip(refs[:3],ids[:3],strict=True))):
            raise ValueError('original skill session changed')
        return pc,pawn,state
    def follow_replacement(self,snapshot):
        """Persistent only: observe a distinct replacement twice, never carry a trend.
        Absence, ambiguous layouts, a returning original, or a pending readback stop.
        No mutation or native refill is performed by this transition.
        """
        if not self.follow:return False
        refs,ids,tid,end,_,key=snapshot
        _,pawn,_=self.scope(snapshot)
        owned=self.owned_skills(pawn)
        if self.record is not snapshot:return True
        if any(identity(s)==ids[3] for s in owned):
            if self.follow_candidate is not None:raise ValueError('original skill reappeared during replacement')
            return False
        if self.pending is not None:raise ValueError('skill replaced with pending refill readback')
        if not owned:raise ValueError('unique ordinary replacement unavailable')
        objs,newkey,_,_,values,_=self.resolve(initial=True,refresh=True)
        self.scope(snapshot)
        if self.record is not snapshot:return True
        newids=tuple(identity(x) for x in objs)
        if (newids[:3]!=ids[:3] or newids[3]==ids[3] or newids[4]==ids[4]
                or newkey[2]==key[2] or set(k[:2] for k in newkey[3]) & set(k[:2] for k in key[3])):
            raise ValueError('replacement is not a distinct skill and pool layout')
        now=self.clock()
        if self.follow_candidate is None:
            self.follow_candidate=(tuple(self.weak(x) for x in objs[3:]),newids[3:],newkey,now)
            self.prev=None;self.pending=None;self.rises=0;self.last_delta=None;self.sample_at=None
            self.record=(refs,ids,tid,end,now+1,key)
            self.report('WAIT: distinct local skill replacement; observing before rearm')
            return True
        newrefs,witness_ids,witness_key,witness_at=self.follow_candidate
        if (newids[3:]!=witness_ids or newkey!=witness_key or not .99<=now-witness_at<=2.5
                or any(r() is None or identity(r())!=i for r,i in zip(newrefs,witness_ids,strict=True))):
            raise ValueError('replacement witness changed or expired')
        self.record=(tuple(self.weak(x) for x in objs),newids,tid,end,now+1,newkey)
        self.follow_candidate=None;self.prev=values;self.pending=None;self.rises=0;self.last_delta=None;self.sample_at=now
        self.report('EXPERIMENT: distinct local skill replacement admitted; fresh trend required')
        return True
    def resolve(self,initial=False,refresh=False):
        pc,pawn,state,ok=self.context()
        if not ok or enum_name(pawn.HealthCondition)!='Healthy': raise ValueError('eligible living local player required')
        if initial:
            owned=self.owned_skills(pawn)
        else:
            refs,ids,tid,_,_,key=self.record
            if self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)) or tuple(identity(x) for x in (pc,pawn,state))!=ids[:3]: raise ValueError('original skill session changed')
            owned=[refs[3]()]
            if refresh:
                owned=self.owned_skills(pawn)
        found=[(s,c) for s in owned for c in candidates(s,pawn,self.ht,self.inline,self.soft_identifier,self.direct_api[3] if self.direct_api is not None else None)]
        if len(found)!=1: raise ValueError('unique ordinary action skill unavailable')
        skill,(script,g,cid,resources,keys,origin,peers)=found[0]
        if self.event_class is not None and (script.Class._path_name()!=CROSSFIRE_CLASS or identity(script.Class)!=self.event_class):
            raise ValueError('exact Cross-Fire script required')
        k=(identity(skill),identity(script),cid,keys,origin)
        if not initial and k!=key: raise ValueError('skill component or pool changed')
        ref=self.construct(self.ref_type,Context=script,ComponentID=g)
        if identity(ref.Context)!=identity(script) or guid(ref.ComponentID)!=cid: raise ValueError('constructed reference mismatch')
        values=[];raw=[]
        for h in resources:
            p,cur,maxv=(numeric(f(ref,h)) for f in self.api[:3])
            if not 0<=p<=1 or not 0<=cur<=maxv<=1e9 or maxv<=0 or abs(p-cur/maxv)>.005: raise ValueError('skill ratio ambiguous')
            values.append(p);raw.append((cur,maxv))
        if self.adaptive_api is not None:
            expected=values[0 if self.mode=='cooldown' else 1]
            for actual in (numeric(self.adaptive_api[0](pawn)),numeric(self.adaptive_api[1](ref))):
                if not 0<=actual<=1 or abs(actual-expected)>.005: raise ValueError('native action skill percent disagrees with selected resource')
        named=None
        if peers:
            cur,p=direct_sample(self.direct_api,pawn,resources[0],self.ht)
            maxv=raw[0][1]
            if abs(p-values[0])>.005 or abs(cur-raw[0][0])>maxv*.005 or abs(cur/maxv-p)>.005:
                raise ValueError('named main cooldown disagrees with component')
            if not initial and maxv!=self.named_max:raise ValueError('named main cooldown maximum changed')
            named=(cur,maxv,tuple(direct_sample(self.direct_api,pawn,h,self.ht) for h in peers))
        # Getter calls can invalidate inline or external definitions or membership.
        # Re-resolve the complete selected candidate before every native dispatch.
        if refresh or (initial and peers):
            again=[(s,c) for s in self.owned_skills(pawn) for c in candidates(s,pawn,self.ht,self.inline,self.soft_identifier,self.direct_api[3] if self.direct_api is not None else None)]
            if len(again)!=1:raise ValueError('skill layout changed during getters')
            selected,a=again[0]
            if (identity(selected),identity(a[0]),a[2],a[4],a[5])!=k:
                raise ValueError('skill layout changed during getters')
        return (pc,pawn,state,skill,script),k,ref,resources,tuple(values),named
    def begin(self):
        if self.record or self.fault or self.busy:return False
        try:
            objs,key,_,_,v,named=self.resolve(True);now=self.clock()
            self.named_max=named[1] if named is not None else None
            self.record=(tuple(self.weak(x) for x in objs),tuple(identity(x) for x in objs),self.thread(),math.inf if self.continuous else now+30,now+1,key)
            self.prev=v;self.pending=None;self.rises=0;self.sample_at=now;self.last_delta=None;self.follow_candidate=None;self.event_active=False
        except Exception as e:self.report('HOLD: skill assist '+str(e)[:120]);return False
        self.report('EXPERIMENT: '+('named main cooldown' if named is not None else self.mode)+' assist armed '+('for this session' if self.continuous else 'for 30 seconds'));return True
    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.pending=None;self.prev=None;self.rises=0;self.sample_at=None;self.last_delta=None;self.follow_candidate=None;self.event_active=False;self.event_epoch+=1
            self.report('STOP: skill assist '+reason+'; no future refill; recovered resource not reversed')
    def tick(self,permitted):
        if self.record is None or self.busy:return
        now=self.clock();refs,ids,tid,end,due,key=self.record
        if not permitted or self.thread()!=tid or now>=end:self.stop('permission/thread/lifetime ended');return
        if now<due:return
        snapshot=self.record;epoch=self.event_epoch;self.busy=True
        try:
            try:
                if self.follow_replacement(snapshot):return
                _,_,ref,h,v,named=self.resolve()
            except Exception as e:self.stop(str(e)[:100]);return
            if self.record is not snapshot:return
            self.record=(refs,ids,tid,end,now+1,key)
            idx=0 if self.mode=='cooldown' else 1
            if self.event_class is not None and (not self.event_active or epoch!=self.event_epoch or self.prev is None):
                self.prev=v if self.event_active else None
                self.sample_at=now if self.event_active else None
                self.rises=0;self.last_delta=None;return
            p=v[idx];old=self.prev[idx];self.prev=v
            # A depleted duration or unexplained upward jump is a conservative
            # end/reset witness, even when the named end event was missed.
            # Ignore only the first sample after our own verified refill.
            if self.event_class is not None and (p<=.05 or (self.pending is None and p>old+.005)):
                self.event_active=False;self.event_epoch+=1
                self.prev=None;self.pending=None;self.sample_at=None;self.rises=0;self.last_delta=None
                return
            elapsed=None if self.sample_at is None else now-self.sample_at
            self.sample_at=now
            if self.pending is not None:
                # Immediate verification occurs after dispatch; discard the next sample as trend evidence.
                self.pending=None;self.rises=0;self.last_delta=None;return
            # Cooldown: only already rising. Duration: only already draining. Never reset/full refill.
            trend=p>old+.0001 if idx==0 else p<old-.0001
            self.rises=self.rises+1 if trend else 0
            if self.adaptive_api is not None:
                if elapsed is None or not .99<=elapsed<=1.5 or not trend or self.rate==1.:
                    self.rises=0;self.last_delta=None;return
                delta=abs(p-old)
                # Community reports normal cooldown progress in raw seconds;
                # large jumps may be skill refunds, not natural recharge.
                if named is not None and delta*named[1]>5.*elapsed:
                    self.rises=0;self.last_delta=None;return
                previous=self.last_delta;self.last_delta=delta
                if previous is None:return
                amount=min(.03,(self.rate-1)*min(previous,delta))
                if amount<=.0001:return
            else:amount=.01
            if self.rises<2 or not .05<p<.90:return
            try:
                fresh=self.resolve(refresh=True);freshp=fresh[4][idx]
                if named is not None:
                    if fresh[5] is None or abs(named[1]-fresh[5][1])>1e-5 or abs(named[0]-fresh[5][0])>fresh[5][1]*.005:
                        raise ValueError('named main cooldown changed before refill')
                last=self.context()
                if not last[3] or tuple(identity(x) for x in last[:3])!=ids[:3] or self.thread()!=tid:raise ValueError('session changed before skill refill')
                if self.record is None or self.clock()>=end or abs(freshp-p)>.005 or not .05<freshp<.90 or (idx==0 and freshp<=old) or (idx==1 and freshp>=old):self.stop('resource changed before refill');return
            except Exception as e:self.stop(str(e)[:100]);return
            try:
                if self.adaptive_api is not None:
                    if not 0<=self.clock()-now<=.5:
                        self.rises=0;self.last_delta=None;return
                    amount=min(amount,(self.rate-1)*abs(freshp-old))
                    if amount<=.0001:return
                if self.native_refill is not None:
                    # No native cap parameter: limit requested addition and verify immediately.
                    amount=min(amount,.01)
                cap=min(.95,freshp+amount)
                if self.event_class is not None and (not self.event_active or epoch!=self.event_epoch):return
                if fresh[5] is not None:
                    # Use only the exact selected primary handle, never the
                    # dedicated skill API (which may affect auxiliary/charges).
                    cur,maxv,peers=fresh[5]
                    amount=min((cap-freshp)*maxv, cap*maxv-cur)
                    if not 0<amount<=maxv*.01000001:return
                    self.direct_api[2](fresh[0][1],fresh[3][0],amount)
                elif self.native_refill is not None:
                    self.native_refill(fresh[2],cap-freshp,0) # historical Normal=0; no retry
                else:self.api[3](fresh[2],fresh[3][idx],cap-freshp,cap)
                if self.record is None:
                    if self.native_refill is not None:raise ValueError('scope lost after dedicated refill')
                    return
                observation=self.resolve(refresh=fresh[5] is not None)
                observed=observation[4]
                after=observed[idx]
                if fresh[5] is not None:
                    if observation[5] is None:raise ValueError('named main cooldown lost')
                    cur,maxv,peers=fresh[5];aftercur,aftermax,afterpeers=observation[5]
                    if (abs(aftermax-maxv)>1e-5 or aftercur>cur+amount+.005*maxv or
                            len(peers)!=len(afterpeers) or any(abs(a[0]-b[0])>1e-4 or abs(a[1]-b[1])>.005 for a,b in zip(peers,afterpeers,strict=True))):
                        raise ValueError('named cooldown or excluded resource changed unexpectedly')
                    if aftercur<=cur:self.stop('named cooldown readback ineffective');return
                if self.native_refill is not None:
                    last=self.context()
                    if self.record is None or not last[3] or tuple(identity(x) for x in last[:3])!=ids[:3] or self.thread()!=tid:
                        raise ValueError('scope lost during dedicated refill verification')
                    if abs(observed[1-idx]-fresh[4][1-idx])>.005:
                        raise ValueError('other skill resource changed during dedicated refill')
                if after>cap+.005:raise ValueError('refill exceeded cap')
                if after<=freshp:self.stop('refill readback ineffective');return
                if self.event_class is not None and epoch!=self.event_epoch:
                    self.prev=None;self.sample_at=None;self.pending=None;self.rises=0;self.last_delta=None;return
                self.pending=True;self.rises=0;self.last_delta=None
            except Exception:
                self.fault=True;self.stop('native dispatch/readback uncertain');self.report('FAULT: skill assist; exit game')
        finally:self.busy=False
