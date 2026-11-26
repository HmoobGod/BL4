"""Opt-in bounded local flesh/energy-shield recovery using existing native health-type handles.
No native timer, no constructed tags, no raw pointers or shared definition edits.
Historical declarations and SDK wrapper evidence: SOURCES.md.
"""
import math
from .gameplay_fields import identity
from .weapon_rates import nested, prop

KEY = 'health_pulse'
PERIOD = 1.0
LIFETIME = 30.0
FRACTION = .01
PATH = '/Script/GbxGame.DamageStatics:'
ACTOR = ('Context','ZObjectProperty')
HANDLE = ('HealthType','ZGameDataHandleProperty')
SPECS = {
 'GetHealthPoolLayerOfType': (ACTOR,HANDLE,('bTopDown','ZBoolProperty'),('ReturnValue','ZIntProperty')),
 'GetHealthPoolPercent': (ACTOR,('layer','ZIntProperty'),('ReturnValue','ZFloatProperty')),
 'RefillHealthPercent': (ACTOR,HANDLE,('Percent','ZFloatProperty'),('MaxPercent','ZFloatProperty')),
}

def bind(functions, bind_existing):
    out=[]
    for name,spec in SPECS.items():
        matches=[f for f in functions if f._path_name()==PATH+name]
        if len(matches)!=1:
            raise ValueError('health function missing or ambiguous')
        fn=matches[0]; props=tuple(fn._properties())
        if not props or any(p.ArrayDim != 1 for p in props) or props[0].PropertyClass._path_name()!='/Script/Engine.Actor':
            raise ValueError('health function descriptor mismatch')
        if fn.Outer._path_name()!=PATH[:-1]:
            raise ValueError('health function owner mismatch')
        out.append(bind_existing(functions,PATH+name,spec))
    return tuple(out)

def enum_name(value):
    name=getattr(value,'name',None)
    return name if type(name) is str else None

def numeric(v):
    if type(v) not in (float,int) or not math.isfinite(v):
        raise ValueError('nonfinite health value')
    return float(v)

def select_health(pawn, handle_type, mode):
    if mode not in ('flesh', 'shield'):
        raise ValueError('unknown recovery mode')
    wanted = ('FleshRed', 'IsGeneric') if mode == 'flesh' else ('EnergyBlue', 'IsShield')
    condition=prop(pawn.Class,'HealthCondition','ZEnumProperty')
    if condition.Enum._path_name()!='/Script/OakGame.ECharacterHealthCondition':
        raise ValueError('health condition descriptor mismatch')
    if enum_name(pawn.HealthCondition)!='Healthy':
        raise ValueError('healthy player required; no FFYL recovery')
    health=nested(pawn,'HealthState','OakCharacterHealthState')
    if identity(health.owner)!=identity(pawn) or health.bCurrentlyDead is not False:
        raise ValueError('health owner or living state unavailable')
    disabled=nested(health,'HealingDisabled','GbxAttributeInteger')
    if type(disabled.Value) is not int or disabled.Value!=0:
        raise ValueError('native healing disabled or unknown')
    d=prop(health._type,'HealthTypeStates','ZArrayProperty')
    if type(d.Inner).__name__!='ZStructProperty' or str(d.Inner.Struct.Name)!='HealthTypeState':
        raise ValueError('health layer descriptor mismatch')
    states=health.HealthTypeStates
    if not 0<len(states)<=16:
        raise ValueError('health layers unavailable')
    choices=[]; seen=set()
    for st in states:
        if identity(st._type)!=identity(d.Inner.Struct):
            raise ValueError('health layer wrapper mismatch')
        prop(st._type,'HealthType','ZGameDataHandleProperty')
        h=st.HealthType
        if type(h) is not handle_type:
            raise ValueError('unsupported health handle')
        name=h._name; typ=h._type_handle; addr=identity(h)
        if type(name) is not str or not name.startswith('HealthType_') or type(typ) is not int or not 0<typ<=0xffffffff:
            raise ValueError('unresolved health type identity')
        key=(name,typ,addr)
        if key in seen:
            raise ValueError('duplicate health type')
        seen.add(key)
        color=enum_name(h.DisplayColor); variation=enum_name(h.Variation)
        if color is None or variation is None:
            raise ValueError('unknown health type classification')
        if (color, variation)==wanted:
            choices.append((h,key,st))
    if len(choices)!=1:
        raise ValueError('unique '+mode+' layer unavailable')
    h,key,st=choices[0]
    cur=numeric(nested(st,'SimpleCurrentHealth','GbxAttributeFloat').Value)
    maximum=numeric(nested(st,'SimpleMaxHealth','GbxAttributeFloat').Value)
    if not 0<=cur<=maximum<=1e9 or maximum<=0 or (mode=='flesh' and cur<=0):
        raise ValueError('positive living health ratio unavailable')
    return h,key,cur/maximum

def select_flesh(pawn, handle_type):
    return select_health(pawn, handle_type, 'flesh')

class Pulse:
    def __init__(self,context,weak,handle_type,api,clock,thread,report,mode='flesh',continuous=False,percent=1.0):
        self.context,self.weak,self.handle_type,self.api=context,weak,handle_type,api
        self.clock,self.thread,self.report=clock,thread,report
        self.record=None; self.fault=False; self.busy=False; self.pending=None
        if mode not in ('flesh', 'shield'):
            raise ValueError('unknown recovery mode')
        self.mode=mode; self.continuous=continuous is True; self.observed=None; self.rises=0
        self.fraction=FRACTION
        self.update_rate(percent)

    def update_rate(self,percent):
        if type(percent) not in (int,float) or not math.isfinite(percent) or not .1<=percent<=1.:
            raise ValueError('recovery pulse percentage out of range')
        if not self.continuous and percent!=1.:
            raise ValueError('manual recovery uses fixed pulse')
        self.fraction=percent/100.

    def resolve(self):
        pc,pawn,state,eligible=self.context()
        if not eligible:
            raise ValueError('solo permission lost')
        if self.record is not None:
            refs,ids,tid,_,_,expected=self.record
            if self.thread()!=tid or any(r() is None or identity(r())!=i or identity(o)!=i for r,i,o in zip(refs,ids,(pc,pawn,state),strict=True)):
                raise ValueError('original session changed')
        h,key,ratio=select_health(pawn,self.handle_type,self.mode)
        layer=self.api[0](pawn,h,False)
        if type(layer) is not int or not 0<=layer<16:
            raise ValueError('native selected layer unavailable')
        p=numeric(self.api[1](pawn,layer))
        # Only use a normalized getter when its independent simple ratio agrees.
        # No guessing between percent units (community reader observes both possibilities).
        if not 0<=p<=1 or (self.mode=='flesh' and p<=0) or abs(p-ratio)>0.005:
            raise ValueError('normalized health readback ambiguous')
        if self.record is not None and (key,layer)!=expected:
            raise ValueError('selected layer identity changed')
        return (pc,pawn,state),h,(key,layer),p

    def begin(self):
        if self.record is not None or self.fault or self.busy:
            return False
        try:
            objs,_,key,p=self.resolve(); now=self.clock()
            self.observed=p; self.rises=0; self.pending=None
            self.record=(tuple(self.weak(x) for x in objs),tuple(identity(x) for x in objs),self.thread(),(math.inf if self.continuous else now+LIFETIME),now+PERIOD,key)
        except Exception as exc:
            self.report('HOLD: health pulse preflight: '+str(exc)[:120]); return False
        self.report('EXPERIMENT: '+self.mode+' recovery armed '+('for this session' if self.continuous else 'for 30 seconds')+'; no native timer.'); return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None
            self.pending=None
            self.observed=None; self.rises=0
            self.report('STOP: health pulse '+reason+'; no further healing dispatched.')

    def tick(self,permitted):
        if self.record is None or self.busy: return
        now=self.clock(); refs,ids,tid,end,due,key=self.record
        if not permitted or self.thread()!=tid or now>=end:
            self.stop('permission, thread or lifetime ended'); return
        if now<due: return
        snapshot=self.record
        self.busy=True
        try:
            try:
                objs,h,_,p=self.resolve()
            except Exception as exc:
                self.stop(str(exc)[:100]); return
            if self.record is not snapshot:
                return
            self.record=(refs,ids,tid,end,now+PERIOD,key) # no catch-up or stacked dispatch
            if self.pending is not None:
                before=self.pending
                self.pending=None
                if p<=before:
                    self.stop('no positive readback after pulse; effect unconfirmed'); return
                if self.mode=='shield':
                    # Own prior pulse could explain this sample. Do not count it as native recharge.
                    self.observed=p; self.rises=0; return
            if self.mode=='shield':
                # Two successive rising samples without a mod pulse. External healing
                # can still explain the rise; this is not a native recharge-state proof.
                self.rises=self.rises+1 if self.observed is not None and p>self.observed+0.0001 else 0
                self.observed=p
                if self.rises<2 or p<=0 or p>=1: return
            if p>=1: return
            # Recheck the original live identity and flesh handle after native reads.
            try:
                fresh=self.context()
                if not fresh[3] or tuple(identity(x) for x in fresh[:3])!=ids:
                    raise ValueError('session changed before refill')
                fresh_h,fresh_key,fresh_ratio=select_health(fresh[1],self.handle_type,self.mode)
                if fresh_key!=key[0] or abs(fresh_ratio-p)>0.005 or (self.mode=='shield' and fresh_ratio+1e-6<p):
                    raise ValueError('selected layer identity or value changed before refill')
                if self.continuous:
                    last=self.context()
                    if not last[3] or tuple(identity(x) for x in last[:3])!=ids or self.thread()!=tid:
                        raise ValueError('session changed after final layer read')
                if self.clock()>=end or self.record is None or fresh_ratio>=1:
                    self.stop('lifetime ended before refill'); return
            except Exception as exc:
                self.stop(str(exc)[:100]); return
            try:
                # Native refill only; no direct HP edit. MaxPercent is bounded to 1.
                self.api[2](fresh[1],fresh_h,min(self.fraction,1-max(p,fresh_ratio)),1.0)
                if self.record is not None:
                    self.pending=max(p,fresh_ratio)
            except Exception:
                self.fault=True; self.stop('native dispatch uncertain; do not retry')
                self.report('FAULT: health pulse native dispatch uncertain. Exit game immediately.')
        finally:
            self.busy=False
