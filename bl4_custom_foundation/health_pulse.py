"""Opt-in bounded local flesh/energy-shield recovery using existing native health-type handles.
Legacy pulse has no native timer; NativeOvertime is a separate one-shot native timer experiment.
No constructed tags, raw pointers or shared definition edits.
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

# Separate native engine-timed experiment; not the existing Python pulse loop.
OVERTIME_NAME = 'RefillHealthPercentOvertime'
OVERTIME_SPEC = (ACTOR,HANDLE,('Percent','ZFloatProperty'),('MaxPercent','ZFloatProperty'),('Duration','ZFloatProperty'),('TickRate','ZFloatProperty'),('ReturnValue','ZIntProperty'))


def bind_overtime(functions, bind_existing):
    out=[]
    for name,spec in tuple(SPECS.items())[:2]+((OVERTIME_NAME,OVERTIME_SPEC),):
        matches=[f for f in functions if f._path_name()==PATH+name]
        if len(matches)!=1: raise ValueError('health overtime function unavailable')
        fn=matches[0]; ps=tuple(fn._properties())
        if not ps or any(p.ArrayDim!=1 for p in ps) or ps[0].PropertyClass._path_name()!='/Script/Engine.Actor' or fn.Outer._path_name()!=PATH[:-1]:
            raise ValueError('health overtime descriptor mismatch')
        out.append(bind_existing(functions,PATH+name,spec))
    return tuple(out)


class NativeOvertime(Pulse):
    """Single small native timed refill, no assumed cancellation/ID mapping.

    The requested native duration and cap are experimental, not proof of expiry.
    Never reissue, never call StopHealthRegen on an unproven ID namespace.
    """
    def __init__(self,context,weak,handle_type,api,clock,thread,report,claim):
        super().__init__(context,weak,handle_type,api,clock,thread,report)
        self.claim=claim; self.dispatched=False; self.native_id=None; self.before=None; self.cap=None; self.verify_at=None

    def begin(self):
        if self.record is not None or self.fault or self.busy or self.dispatched:return False
        try:
            objs,_,key,p=self.resolve(); now=self.clock()
            if not 0<p<.99:raise ValueError('naturally missing flesh health required')
            self.record=(tuple(self.weak(x) for x in objs),tuple(identity(x) for x in objs),self.thread(),now+5,now+1,key)
        except Exception as e:
            self.report('HOLD: native overtime '+str(e)[:100]);return False
        self.report('EXPERIMENT: one native 2-second flesh refill armed; timer cancellation is unverified.');return True

    def stop(self,reason):
        if self.record is None:return
        self.record=None
        if self.dispatched:
            self.fault=True
            self.report('FAULT: native overtime stopped before verification; timer cancellation unverified. Exit game. '+reason)
        else:self.report('STOP: native overtime before dispatch: '+reason)

    def tick(self,permitted):
        if self.record is None or self.busy:return
        snapshot=self.record;refs,ids,tid,end,due,key=snapshot;now=self.clock()
        if not permitted or self.thread()!=tid or now>=end:
            self.stop('permission/thread/observation window ended');return
        if now<due:return
        self.busy=True
        try:
            try:
                objs,h,_,p=self.resolve()
                if self.record is not snapshot:return
                fresh=self.context()
                if not fresh[3] or tuple(identity(x) for x in fresh[:3])!=ids or self.thread()!=tid:raise ValueError('session changed')
                fh,fk,ratio=select_flesh(fresh[1],self.handle_type)
                if fk!=key[0] or abs(p-ratio)>.005:raise ValueError('health identity/value changed')
                last=self.context()
                if not last[3] or tuple(identity(x) for x in last[:3])!=ids or self.thread()!=tid or self.clock()>=end:raise ValueError('session changed after final read')
                if self.record is not snapshot:return
            except Exception as e:
                self.stop(str(e)[:100]);return
            if self.dispatched:
                if max(p,ratio)>self.cap+.005:
                    self.stop('readback exceeded requested cap (external healing also possible)');return
                if now<self.verify_at:return
                self.record=None
                if min(p,ratio)<=self.before:
                    self.fault=True;self.report('FAULT: no positive native overtime readback; exit game.');return
                self.report('EXPERIMENT: positive bounded health readback; native timer expiry and causation unverified. No repeat this process.');return
            if not 0<min(p,ratio) or max(p,ratio)>=.99:
                self.stop('missing health no longer available');return
            # Do not start a timer if the callback arrived too late to observe it.
            if self.clock()+3>=end:
                self.stop('insufficient observation window');return
            if not self.claim():
                self.stop('one native timed attempt per process');return
            self.before=max(p,ratio); self.cap=min(1.,self.before+.01)
            self.dispatched=True;self.verify_at=self.clock()+2.5
            try:
                result=self.api[2](fresh[1],fh,min(.01,self.cap-self.before),self.cap,2.,.5)
                if type(result) is not int or not 0<result<=2**31-1:
                    raise ValueError('native timer ID not positive')
                self.native_id=result
                if self.record is not snapshot:return
                self.report('EXPERIMENT: native timed refill dispatched; no further call will be issued.')
            except Exception:
                self.fault=True;self.record=None;self.report('FAULT: native overtime dispatch/ID uncertain. Exit game.')
        finally:self.busy=False

# Distinct Start/StopHealthRegen experiment. Construct only a constant initializer
# and pass the existing unique flesh definition's tag container, never edit it.
REGEN_START='StartHealthRegen'
REGEN_STOP='StopHealthRegen'
INIT='/Script/GbxEngine.GbxAttributeInit'
TAG_CONTAINER='/Script/GameplayTags.GameplayTagContainer'
TAG='/Script/GameplayTags.GameplayTag'
REGEN_SPECS={REGEN_START:(ACTOR,('Duration','ZFloatProperty'),('RegenRate','ZStructProperty'),('bStopWhenFull','ZBoolProperty'),('TickRate','ZFloatProperty'),('HealthTags','ZStructProperty'),('ReturnValue','ZIntProperty')),
             REGEN_STOP:(ACTOR,('ID','ZIntProperty'))}


def bind_regen(functions, existing):
    out=[]; init_type=tag_type=None
    for name,sig in tuple(SPECS.items())[:2]+tuple(REGEN_SPECS.items()):
        matches=[f for f in functions if f._path_name()==PATH+name]
        if len(matches)!=1:raise ValueError('native regen function unavailable: '+name)
        fn=matches[0]; ps=tuple(fn._properties())
        if (len(ps)!=len(sig) or any(p.ArrayDim!=1 for p in ps) or fn.Outer._path_name()!=PATH[:-1]
                or ps[0].PropertyClass._path_name()!='/Script/Engine.Actor'):
            raise ValueError('native regen signature mismatch')
        if name==REGEN_START:
            init_type=ps[2].Struct;tag_type=ps[5].Struct
            if init_type._path_name()!=INIT or tag_type._path_name()!=TAG_CONTAINER:
                raise ValueError('regen struct descriptor mismatch')
        out.append(existing(functions,PATH+name,sig))
    return tuple(out),init_type,tag_type


def regen_rate(make,init_type,handle_type,def_type):
    rate=make(INIT,True,constant=.01,PostScale=1.)
    if rate._type._path_name()!=INIT or identity(rate._type)!=identity(init_type):raise ValueError('regen initializer wrapper mismatch')
    for n in ('constant','PostScale'):prop(rate._type,n,'ZFloatProperty')
    if abs(numeric(rate.constant)-.01)>1e-8 or numeric(rate.PostScale)!=1.:raise ValueError('regen initializer readback mismatch')
    prop(rate._type,'attribute','ZGameDataHandleProperty')
    a=rate.attribute
    if type(a) is not handle_type or a._name!='None' or type(a._type_handle) is not int or a._type_handle!=0:
        raise ValueError('regen initializer attribute is not empty')
    table=nested(rate,'DataTableValue','DataTableValueHandle')
    prop(table._type,'DataTable','ZGbxDefPtrProperty')
    prop(table._type,'RowName','ZNameProperty');prop(table._type,'ColumnName','ZNameProperty')
    dt=table.DataTable
    if type(dt) is not def_type or dt._name!='None' or dt._type is not None or str(table.RowName)!='None' or str(table.ColumnName)!='None':
        raise ValueError('regen initializer data table is not empty')
    return rate


def regen_tags(pawn,handle_type,tag_type,expected):
    # Select from existing health definitions only. Explicit tags must be
    # nonempty and unique to flesh, including hierarchical prefix matching.
    h,key,ratio=select_flesh(pawn,handle_type)
    if key!=expected:raise ValueError('regen flesh identity changed')
    health=nested(pawn,'HealthState','OakCharacterHealthState')
    groups=[];selected=None
    for st in health.HealthTypeStates:
        handle=st.HealthType;tags=handle.GameplayTags
        if tags._type._path_name()!=TAG_CONTAINER or identity(tags._type)!=identity(tag_type):raise ValueError('regen tag container mismatch')
        sets=[]
        for name in ('GameplayTags','ParentTags'):
            d=prop(tags._type,name,'ZArrayProperty').Inner
            if type(d).__name__!='ZStructProperty' or d.Struct._path_name()!=TAG:raise ValueError('regen tag array mismatch')
            arr=getattr(tags,name)
            if len(arr)>64:raise ValueError('regen tag count excessive')
            names=[]
            for entry in arr:
                if identity(entry._type)!=identity(d.Struct):raise ValueError('regen tag wrapper mismatch')
                prop(entry._type,'TagName','ZNameProperty')
                n=str(entry.TagName)
                if not n or n=='None' or any(not part or not all(c.isalnum() or c=='_' for c in part) for part in n.split('.')):raise ValueError('invalid regen tag')
                names.append(n.casefold())
            if len(names)!=len(set(names)):raise ValueError('duplicate regen tag')
            sets.append(tuple(sorted(names)))
        explicit,parents=sets
        if not explicit or any(not any(x.startswith(parent+'.') for x in explicit) for parent in parents):
            raise ValueError('unclassified or incoherent health layer tags')
        if handle._name==h._name and identity(handle)==identity(h):selected=(tags,explicit,parents)
        else:groups.append((handle._name,identity(handle),explicit,parents))
    if selected is None:raise ValueError('flesh tag container missing')
    tags,explicit,parents=selected
    if len(explicit)!=1:raise ValueError('unique flesh-only explicit tag required')
    target=explicit[0]
    for _,_,other,otherparents in groups:
        if any(target==x or target.startswith(x+'.') or x.startswith(target+'.') for x in other) or target in otherparents:
            raise ValueError('flesh tag overlaps another health layer')
    return tags,(explicit,parents,tuple(groups)),ratio


class NativeRegen(Pulse):
    """One bounded native regeneration lease, not permanent passive regen.

    Stop is deferred to the original monitor thread; no cleanup against a
    replacement pawn or after the requested expiry (ID reuse unproven).
    """
    def __init__(self,context,weak,handle_type,api,clock,thread,report,claim,make,init_type,tag_type,def_type,cleanup_context):
        super().__init__(context,weak,handle_type,api,clock,thread,report)
        self.claim,self.make,self.init_type,self.tag_type,self.def_type,self.cleanup_context=claim,make,init_type,tag_type,def_type,cleanup_context
        self.dispatched=False;self.native_id=None;self.stop_requested=False;self.started=None;self.tag_key=None;self.before=None
    def begin(self):
        if self.record is not None or self.fault or self.busy or self.dispatched:return False
        try:
            objs,_,key,p=self.resolve();now=self.clock()
            if not 0<p<.97:raise ValueError('naturally missing flesh health required')
            _,self.tag_key,_=regen_tags(objs[1],self.handle_type,self.tag_type,key[0])
            regen_rate(self.make,self.init_type,self.handle_type,self.def_type)
            self.record=(tuple(self.weak(x) for x in objs),tuple(identity(x) for x in objs),self.thread(),now+5,now+1,key)
        except Exception as exc:
            self.report('HOLD: native regeneration '+str(exc)[:100]);return False
        self.report('EXPERIMENT: native regeneration start/stop armed; rate and lifetime unverified.');return True
    def fail(self,reason):
        self.fault=True;self.record=None
        self.report('FAULT: native regeneration '+reason+'; exit game, do not travel.')
    def stop(self,reason):
        if self.record is None:return
        if not self.dispatched:
            self.record=None;self.report('STOP: native regeneration before dispatch: '+reason)
        else:
            self.stop_requested=True
            self.report('STOP PENDING: native regeneration; wait for original game hook, then exit game.')
    def cleanup(self,snapshot,now,anomaly=False):
        refs,ids,tid,_,_,key=snapshot
        try:
            if self.native_id is None or self.thread()!=tid or now>=self.started+2.:raise ValueError('original native ID window unavailable')
            pc,pawn,state,eligible=self.cleanup_context()
            if not eligible or any(r() is None or identity(r())!=i or identity(o)!=i for r,i,o in zip(refs,ids,(pc,pawn,state),strict=True)):
                raise ValueError('original solo session unavailable')
            _,fk,ratio=select_flesh(pawn,self.handle_type)
            if fk!=key[0] or ratio>=1.:raise ValueError('original health identity lost or native stop-when-full may have retired ID')
            last=self.cleanup_context()
            if (not last[3] or tuple(identity(x) for x in last[:3])!=ids or self.thread()!=tid
                    or self.clock()>=self.started+2. or self.record is not snapshot):
                raise ValueError('native stop window or original session ended')
            _,final_key,final_ratio=select_flesh(last[1],self.handle_type)
            if final_key!=key[0] or final_ratio>=1. or self.clock()>=self.started+2. or self.record is not snapshot:
                raise ValueError('health identity or native ID window changed after final scope')
            self.api[3](last[1],self.native_id)
        except Exception as e:
            self.fail('cleanup uncertain: '+str(e)[:100]);return
        self.record=None
        if anomaly:
            self.fail('unexpected health increase; matching stop dispatched, cancellation unverified');return
        self.report('EXPERIMENT: matching native stop dispatched; cancellation/expiry unverified. Exit game after test.')
    def tick(self,permitted):
        if self.record is None or self.busy:return
        snapshot=self.record;refs,ids,tid,end,due,key=snapshot;now=self.clock()
        self.busy=True
        try:
            if self.dispatched:
                if not permitted or self.stop_requested or self.thread()!=tid or now>=self.started+2.:
                    self.cleanup(snapshot,self.clock());return
                try:
                    objs,_,_,p=self.resolve()
                    _,tag_key,ratio=regen_tags(objs[1],self.handle_type,self.tag_type,key[0])
                    if tag_key!=self.tag_key or abs(p-ratio)>.005:raise ValueError('health or tags changed during regen')
                    last=self.context()
                    if not last[3] or tuple(identity(x) for x in last[:3])!=ids or self.thread()!=tid:raise ValueError('session changed during regen')
                except Exception:
                    self.cleanup(snapshot,self.clock());return
                if p>=1. or ratio>=1.:
                    self.fail('full health observed; native stop-when-full may have retired ID');return
                anomaly=max(p,ratio)>self.before+.025
                if self.stop_requested or self.clock()>=self.started+1. or anomaly:
                    self.report('EXPERIMENT: flesh readback '+('increased (causation unverified)' if p>self.before else 'did not increase')+'.')
                    self.cleanup(snapshot,self.clock(),anomaly=anomaly);return
                return
            if not permitted or self.thread()!=tid or now>=end:
                self.stop('permission/thread/window ended');return
            if now<due:return
            try:
                objs,_,_,p=self.resolve();rate=regen_rate(self.make,self.init_type,self.handle_type,self.def_type)
                fresh=self.context()
                if not fresh[3] or tuple(identity(x) for x in fresh[:3])!=ids or self.thread()!=tid:raise ValueError('session changed')
                tags,tag_key,ratio=regen_tags(fresh[1],self.handle_type,self.tag_type,key[0])
                if tag_key!=self.tag_key or abs(p-ratio)>.005 or not 0<min(p,ratio) or max(p,ratio)>=.97:raise ValueError('health or tags changed')
                last=self.context()
                if not last[3] or tuple(identity(x) for x in last[:3])!=ids or self.thread()!=tid or self.clock()+2.>=end:raise ValueError('session/window changed before start')
                tags,final_tag_key,final_ratio=regen_tags(last[1],self.handle_type,self.tag_type,key[0])
                if final_tag_key!=self.tag_key or abs(final_ratio-p)>.005 or not 0<final_ratio<.97 or self.clock()+2.>=end:
                    raise ValueError('health or tags changed after final session scope')
                if self.record is not snapshot:return
                if not self.claim():self.stop('one native timed attempt per process');return
            except Exception as exc:
                self.stop(str(exc)[:100]);return
            self.before=max(p,ratio,final_ratio);self.started=self.clock();self.dispatched=True
            try:
                result=self.api[2](last[1],2.,rate,True,.5,tags)
                if type(result) is not int or not 0<result<=2**31-1:raise ValueError('native regen ID not positive')
                self.native_id=result
                self.report('EXPERIMENT: native regeneration started; matching stop will be attempted on original hook.')
            except Exception as exc:self.fail('start/ID uncertain: '+str(exc)[:100])
        finally:self.busy=False
