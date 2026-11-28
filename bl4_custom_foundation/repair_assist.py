"""One native repair-kit request, on sustained low flesh health. No grants or rate edits."""
from .gameplay_fields import identity
from .weapon_rates import prop, nested
from .health_pulse import select_flesh, numeric

KIT='/Script/OakGame.RepairKit'
PAWN='/Script/OakGame.OakCharacter'
GET='/Script/OakGame.OakInventoryStatics:GetRepairKit'
USE=PAWN+':StartUsingRepairKit'
THRESHOLD=.35


def bind(functions, existing):
    get=[f for f in functions if f._path_name()==GET]
    use=[f for f in functions if f._path_name()==USE]
    if len(get)!=1 or len(use)!=1:raise ValueError('unique repair kit functions unavailable')
    p=tuple(get[0]._properties());f=use[0]
    if len(p)!=2 or any(x.ArrayDim!=1 for x in p) or tuple(x.PropertyClass._path_name() for x in p)!=('/Script/Engine.Actor',KIT):raise ValueError('repair kit getter signature mismatch')
    if f.NumParams!=0 or tuple(f._properties()) or f.Outer._path_name()!=PAWN:raise ValueError('repair request signature mismatch')
    return existing(functions,GET,(('User','ZObjectProperty'),('ReturnValue','ZObjectProperty'))),f


def observe(pawn,kit,handle_type,fn):
    if pawn.Class._path_name()!=PAWN or 'Default__' in pawn._path_name():raise ValueError('exact live local pawn required')
    _,key,pct=select_flesh(pawn,handle_type)
    if (kit is None or kit.Class._path_name()!=KIT or 'Default__' in kit._path_name() or kit.HasAuthority() is not True or kit.IsActorBeingDestroyed() is not False):raise ValueError('live authoritative repair kit required')
    owner=prop(kit.Class,'OwningCharacter','ZObjectProperty')
    if owner.PropertyClass._path_name()!=PAWN or identity(kit.OwningCharacter)!=identity(pawn) or (kit.Owner is not None and identity(kit.Owner)!=identity(pawn)):raise ValueError('repair kit owner mismatch')
    prop(kit.Class,'ActiveCharges','ZIntProperty');prop(kit.Class,'bIsUsing','ZBoolProperty')
    maxattr=nested(kit,'MaxCharges','GbxAttributeInteger');prop(maxattr._type,'Value','ZIntProperty')
    charges,maximum,busy=kit.ActiveCharges,maxattr.Value,kit.bIsUsing
    if type(charges) is not int or type(maximum) is not int or type(busy) is not bool or not 0<=charges<=maximum<=99 or maximum==0:raise ValueError('invalid native repair kit state')
    health=nested(pawn,'HealthState','OakCharacterHealthState')
    minimum=numeric(nested(health,'minhealthpercentmissingtoheal','GbxAttributeFloat').Value)
    if not 0<=minimum<=1:raise ValueError('invalid native missing health threshold')
    call=pawn.StartUsingRepairKit
    if identity(call.func)!=identity(fn) or call.func._path_name()!=USE:raise ValueError('bound repair request mismatch')
    return key,pct,charges,busy,minimum,call


class RepairAssist:
    def __init__(self,context,weak,handle_type,getter,fn,clock,thread,report,can_act):
        self.context,self.weak,self.handle_type,self.getter,self.fn=context,weak,handle_type,getter,fn
        self.clock,self.thread,self.report,self.can_act=clock,thread,report,can_act
        self.record=None;self.fault=False;self.busy=False;self.low=0;self.dispatched=False

    def resolve(self):
        pc,pawn,state,ok=self.context()
        if not ok:raise ValueError('solo permission lost')
        kit=self.getter(pawn);objs=(pc,pawn,state,kit)
        ids=tuple(identity(o) for o in objs)
        if self.record is not None:
            refs,original,tid,end,due,key=self.record
            if self.thread()!=tid or ids!=original or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)):raise ValueError('original repair kit/session changed')
        sample=observe(pawn,kit,self.handle_type,self.fn)
        if self.record is not None and sample[0]!=key:raise ValueError('original health layer changed')
        return objs,ids,sample

    def begin(self):
        if self.record is not None or self.fault or self.busy:return False
        try:
            objs,ids,sample=self.resolve();now=self.clock()
            self.record=(tuple(self.weak(o) for o in objs),ids,self.thread(),now+30,now+.25,sample[0]);self.low=0;self.dispatched=False
        except Exception as exc:self.report('HOLD: repair kit preflight: '+str(exc)[:120]);return False
        self.report('EXPERIMENT: one automatic repair kit request at 35% flesh health or below; close F8.');return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.low=0;self.report('STOP: repair kit '+reason+'; no further requests.')

    def tick(self,permitted):
        if self.record is None or self.busy:return
        refs,ids,tid,end,due,key=self.record;now=self.clock()
        if not permitted or self.thread()!=tid or now>=end:self.stop('permission, thread or lifetime ended');return
        if now<due:return
        snapshot=self.record;self.busy=True
        try:
            try:
                _,_,sample=self.resolve()
                if self.record is not snapshot:return
                self.record=(refs,ids,tid,end,now+.25,key)
                if not self.can_act():self.low=0;return
                _,pct,charges,using,minimum,_=sample
                self.low=self.low+1 if 0<pct<=THRESHOLD and charges>0 and not using and 1-pct>=minimum else 0
                if self.low<2:return
                pending=self.record
                _,_,fresh=self.resolve()
                if self.record is not pending:return
                _,pct,charges,using,minimum,call=fresh
                if not (0<pct<=THRESHOLD and charges>0 and not using and 1-pct>=minimum):self.low=0;return
                last=self.context()
                if not last[3] or tuple(identity(o) for o in last[:3])!=ids[:3] or self.thread()!=tid or self.clock()>=end or self.record is not pending or not self.can_act():self.stop('scope changed before dispatch');return
            except Exception as exc:self.stop(str(exc)[:100]);return
            # Consume the arm BEFORE dispatch. Native readiness/acceptance is not proven.
            self.dispatched=True;self.record=None;self.low=0
            try:call();self.report('EXPERIMENT: native repair request dispatched; charge consumption/healing unverified.')
            except Exception:self.fault=True;self.report('FAULT: repair request uncertain; exit game; no retry.')
        finally:self.busy=False
