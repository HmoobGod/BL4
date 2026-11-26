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


def candidates(skill,pawn,ht,inline,soft_identifier=None):
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
            if not any(cid) or any(guid(d.ChargeComponentID)) or len(d.AuxCooldownPoolDefs): raise ValueError('charge/auxiliary skill unsupported')
            definitions=(d.CooldownPoolDef,d.DurationPoolDef)
            keys=tuple(handle(h,ht) for h in definitions)
            resources=tuple(h.resource for h in definitions)
            rk=tuple(handle(h,ht) for h in resources)
            if len({k[:2] for k in keys+rk})!=4 or len({k[2] for k in keys+rk})!=4: raise ValueError('ambiguous skill pool identity')
            out.append((s,d.ComponentID,cid,resources,keys+rk,(origin,tuple(layout))))
    return out

class SkillPulse:
    def __init__(self,context,weak,ht,inline,construct,ref_type,api,find,clock,thread,report,mode,continuous=False,adaptive_api=None,rate=2.,soft_identifier=None,follow=False):
        if mode not in ('cooldown','duration'): raise ValueError('unknown skill mode')
        self.context,self.weak,self.ht,self.inline,self.construct,self.ref_type,self.api,self.find=context,weak,ht,inline,construct,ref_type,api,find
        self.clock,self.thread,self.report,self.mode=clock,thread,report,mode
        self.continuous=continuous is True
        self.follow=self.continuous and follow is True
        self.soft_identifier=soft_identifier
        self.record=None;self.fault=False;self.busy=False;self.prev=None;self.pending=None;self.rises=0;self.follow_candidate=None
        if adaptive_api is not None and (not self.continuous or len(adaptive_api)!=2): raise ValueError('adaptive mode requires continuous and two getters')
        self.adaptive_api=adaptive_api;self.rate=2.;self.sample_at=None;self.last_delta=None
        self.update_adaptive_rate(rate)
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
        objs,newkey,_,_,values=self.resolve(initial=True,refresh=True)
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
        found=[(s,c) for s in owned for c in candidates(s,pawn,self.ht,self.inline,self.soft_identifier)]
        if len(found)!=1: raise ValueError('unique ordinary action skill unavailable')
        skill,(script,g,cid,resources,keys,origin)=found[0]
        k=(identity(skill),identity(script),cid,keys,origin)
        if not initial and k!=key: raise ValueError('skill component or pool changed')
        ref=self.construct(self.ref_type,Context=script,ComponentID=g)
        if identity(ref.Context)!=identity(script) or guid(ref.ComponentID)!=cid: raise ValueError('constructed reference mismatch')
        values=[]
        for h in resources:
            p,cur,maxv=(numeric(f(ref,h)) for f in self.api[:3])
            if not 0<=p<=1 or not 0<=cur<=maxv<=1e9 or maxv<=0 or abs(p-cur/maxv)>.005: raise ValueError('skill ratio ambiguous')
            values.append(p)
        if self.adaptive_api is not None:
            expected=values[0 if self.mode=='cooldown' else 1]
            for actual in (numeric(self.adaptive_api[0](pawn)),numeric(self.adaptive_api[1](ref))):
                if not 0<=actual<=1 or abs(actual-expected)>.005: raise ValueError('native action skill percent disagrees with selected resource')
        # Getter calls can invalidate inline or external definitions or membership.
        # Re-resolve the complete selected candidate before every native dispatch.
        if refresh:
            again=[(s,c) for s in self.owned_skills(pawn) for c in candidates(s,pawn,self.ht,self.inline,self.soft_identifier)]
            if len(again)!=1:raise ValueError('skill layout changed during getters')
            selected,a=again[0]
            if (identity(selected),identity(a[0]),a[2],a[4],a[5])!=k:
                raise ValueError('skill layout changed during getters')
        return (pc,pawn,state,skill,script),k,ref,resources,tuple(values)
    def begin(self):
        if self.record or self.fault or self.busy:return False
        try:
            objs,key,_,_,v=self.resolve(True);now=self.clock()
            self.record=(tuple(self.weak(x) for x in objs),tuple(identity(x) for x in objs),self.thread(),math.inf if self.continuous else now+30,now+1,key)
            self.prev=v;self.pending=None;self.rises=0;self.sample_at=now;self.last_delta=None;self.follow_candidate=None
        except Exception as e:self.report('HOLD: skill assist '+str(e)[:120]);return False
        self.report('EXPERIMENT: '+self.mode+' assist armed '+('for this session' if self.continuous else 'for 30 seconds'));return True
    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.pending=None;self.prev=None;self.rises=0;self.sample_at=None;self.last_delta=None;self.follow_candidate=None
            self.report('STOP: skill assist '+reason+'; no future refill; recovered resource not reversed')
    def tick(self,permitted):
        if self.record is None or self.busy:return
        now=self.clock();refs,ids,tid,end,due,key=self.record
        if not permitted or self.thread()!=tid or now>=end:self.stop('permission/thread/lifetime ended');return
        if now<due:return
        snapshot=self.record;self.busy=True
        try:
            try:
                if self.follow_replacement(snapshot):return
                _,_,ref,h,v=self.resolve()
            except Exception as e:self.stop(str(e)[:100]);return
            if self.record is not snapshot:return
            self.record=(refs,ids,tid,end,now+1,key)
            idx=0 if self.mode=='cooldown' else 1
            p=v[idx];old=self.prev[idx];self.prev=v
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
                previous=self.last_delta;self.last_delta=delta
                if previous is None:return
                amount=min(.03,(self.rate-1)*min(previous,delta))
                if amount<=.0001:return
            else:amount=.01
            if self.rises<2 or not .05<p<.90:return
            try:
                fresh=self.resolve(refresh=True);freshp=fresh[4][idx]
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
                cap=min(.95,freshp+amount)
                self.api[3](fresh[2],fresh[3][idx],cap-freshp,cap)
                if self.record is None:return
                after=self.resolve()[4][idx]
                if after>cap+.005:raise ValueError('refill exceeded cap')
                if after<=freshp:self.stop('refill readback ineffective');return
                self.pending=True;self.rises=0;self.last_delta=None
            except Exception:
                self.fault=True;self.stop('native dispatch/readback uncertain');self.report('FAULT: skill assist; exit game')
        finally:self.busy=False
