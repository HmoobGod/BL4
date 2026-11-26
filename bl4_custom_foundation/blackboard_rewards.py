"""Opt-in native reward attribute trial. Never grants rewards or creates entries.
Native serialization evidence is a conservative admission experiment, not ABI proof.
"""
import math
import re
from .gameplay_fields import identity
from .weapon_rates import prop
from .double_jump import struct

ENGINE='/Script/GbxEngine.'
DEF=ENGINE+'GbxAttributeDef'
ENTRY=ENGINE+'GbxBlackboardEntryRef'
PARAM=ENGINE+'GbxParam'
TARGETS={'progress_enemy_xp':'Att_CombatXP_Multiplier','progress_money':'Att_PickupCash_Multiplier','progress_eridium':'Att_PickupEridium_Multiplier'}
MISSING='BL4Custom_Unused_Reward_Probe_6F79B1'
S='ZStructProperty'; O='ZObjectProperty'; F='ZFloatProperty'; N='ZNameProperty'; T='ZStrProperty'
SPECS={
 'GetBlackboardParamPure':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('OwnerContext',O),('bReportIfMissing','ZBoolProperty'),('ReturnValue',S))),
 'GetBlackboardFloatPure':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('OwnerContext',O),('bReportIfMissing','ZBoolProperty'),('ReturnValue',F))),
 'SetBlackboardParam':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('Value',S),('OwnerContext',O))),
 'Conv_FloatToGbxParam':('GbxParamBlueprintLibrary',(('Value',F),('ReturnValue',S))),
 'Conv_IntToGbxParam':('GbxParamBlueprintLibrary',(('Value','ZIntProperty'),('ReturnValue',S))),
 'Conv_DoubleToGbxParam':('GbxParamBlueprintLibrary',(('Value','ZDoubleProperty'),('ReturnValue',S))),
 'Conv_StringToGbxParam':('GbxParamBlueprintLibrary',(('Value',T),('ReturnValue',S))),
 'Conv_GbxParamToString':('GbxParamBlueprintLibrary',(('GbxParam',S),('ReturnValue',T))),
 'GetGbxParam_Float':('GbxParamBlueprintLibrary',(('GbxParam',S),('Context',O),('ReturnValue',F))),
 'GetSummary_GbxParam':('GbxParamBlueprintLibrary',(('Param',S),('ReturnValue',T))),
 'GetValueOfAttribute':('GbxAttributeBlueprintLibrary',(('AttributeDef',N),('ContextSource',O),('DefaultValue',F),('ReturnValue',F))),
}

def near(a,b):return math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-7)
def number(v):
    if type(v) not in (int,float) or not math.isfinite(v) or not 0<float(v)<=100:raise ValueError('positive bounded reward multiplier required')
    return float(v)

class Binding:
    def __init__(self,functions,bound,make,def_type,def_struct,wrapper):
        self.make,self.def_type,self.def_struct,self.wrapper=make,def_type,def_struct,wrapper
        self.calls={};self.types={}
        if def_struct._path_name()!=DEF:raise ValueError('unexpected attribute definition type')
        for name,(lib,sig) in SPECS.items():
            path=ENGINE+lib+':'+name
            fs=[f for f in functions if f._path_name()==path]
            if len(fs)!=1:raise ValueError('missing or ambiguous native API: '+name)
            fn=fs[0];ps=tuple(fn._properties())
            if fn.Outer._path_name()!=ENGINE+lib or fn.NumParams!=len(sig) or tuple((str(p.Name),type(p).__name__) for p in ps)!=sig or any(p.ArrayDim!=1 for p in ps):raise ValueError('native reward signature mismatch: '+name)
            for p in ps:
                if type(p).__name__==O and p.PropertyClass._path_name()!='/Script/CoreUObject.Object':raise ValueError('unexpected owner argument')
                if type(p).__name__==S:
                    expected=ENTRY if str(p.Name)=='BlackboardKey' else PARAM
                    if p.Struct._path_name()!=expected:raise ValueError('unexpected parameter struct')
                    old=self.types.setdefault(expected,p.Struct)
                    if identity(old)!=identity(p.Struct):raise ValueError('parameter type identity differs')
            self.calls[name]=bound(functions,path,sig)
    def check(self,obj,path):
        if type(obj) is not self.wrapper or obj._type._path_name()!=path or identity(obj._type)!=identity(self.types[path]):raise ValueError('unexpected returned native struct')
        return obj
    def key(self,name):
        prop(self.types[ENTRY],'Name',N)
        result=self.check(self.make(self.types[ENTRY],Name=name),ENTRY)
        if result.Name!=name:raise ValueError('blackboard key mismatch')
        return result
    def definition(self,name):
        d=self.def_type(name,self.def_struct,True)
        if type(d) is not self.def_type or d._name!=name or identity(d._type)!=identity(self.def_struct):raise ValueError('unresolved reward definition')
        for k in ('Context','Value'):prop(d._type,k,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if c._type._path_name()!=ENGINE+'GbxBlackboardOwnerContextResolver' or v._type._path_name()!=ENGINE+'GbxBlackboardValueResolver':raise ValueError('not an exact blackboard resolver')
        k=struct(v,'Variable',ENTRY)
        if k.Name!=name:raise ValueError('reward variable mismatch')
        return (identity(d),identity(c._type),identity(v._type),name)
    def get(self,name,pawn):
        r=self.calls['GetBlackboardParamPure'](self.key(name),pawn,False)
        if type(r) is not tuple or len(r)!=2 or self.check(r[1],ENTRY).Name!=name:raise ValueError('unexpected blackboard read tuple')
        return self.check(r[0],PARAM)
    def fingerprint(self,p):
        self.check(p,PARAM)
        out=[]
        for n in ('Conv_GbxParamToString','GetSummary_GbxParam'):
            r=self.calls[n](p)
            if type(r) is not tuple or len(r)!=2 or type(r[0]) is not str or not len(r[0])<=512:raise ValueError('unexpected native parameter text')
            self.check(r[1],PARAM);out.append(r[0])
        return tuple(out)
    def make_float(self,v):return self.check(self.calls['Conv_FloatToGbxParam'](v),PARAM)
    def typed_float(self,p,v,missing):
        fp=self.fingerprint(p);canonical=self.fingerprint(self.make_float(v))
        # Require actual native type-bearing text, not merely a numeric summary.
        if fp!=canonical or fp==missing or not any(re.match(r'^\s*float\s*[:=(\s]',s,re.I) for s in fp):raise ValueError('existing constant float identity not established')
        for n,x in [('Conv_IntToGbxParam',int(v)),('Conv_DoubleToGbxParam',v),('Conv_StringToGbxParam',str(v))]:
            r=self.calls[n](x)
            if self.fingerprint(self.check(r,PARAM))==fp:raise ValueError('native serialization does not distinguish parameter types')
        return fp
    def absent_witness(self,pawn):
        # Two reserved read-only controls must agree on an explicitly empty or
        # absent representation. No guessed existing-entry creation/clearing.
        names=(MISSING,MISSING+'_B')
        fps=[]
        for n in names:
            fp=self.fingerprint(self.get(n,pawn))
            if not all(not x.strip() or re.fullmatch(r'\s*(?:none|invalid|unset|null|empty)\s*',x,re.I) for x in fp):raise ValueError('missing entry representation is ambiguous')
            r=self.calls['GetBlackboardFloatPure'](self.key(n),pawn,False)
            if type(r) is not tuple or len(r)!=2 or self.check(r[1],ENTRY).Name!=n or type(r[0]) not in (float,int) or r[0]!=0:raise ValueError('missing entry scalar semantics are ambiguous')
            fps.append(fp)
        if fps[0]!=fps[1]:raise ValueError('missing entry witnesses disagree')
        return fps[0]
    def decoded_float(self,p,pawn):
        # Independent native parameter conversion, not Python parsing of diagnostic text.
        r=self.calls['GetGbxParam_Float'](self.check(p,PARAM),pawn)
        if type(r) is not tuple or len(r)!=2 or self.fingerprint(self.check(r[1],PARAM))!=self.fingerprint(p):raise ValueError('native parameter float conversion response uncertain')
        return number(r[0])
    def read(self,name,pawn,missing):
        p=self.get(name,pawn);r=self.calls['GetBlackboardFloatPure'](self.key(name),pawn,False)
        if type(r) is not tuple or len(r)!=2 or self.check(r[1],ENTRY).Name!=name:raise ValueError('unexpected typed float read tuple')
        v=number(r[0]);a=number(self.calls['GetValueOfAttribute'](name,pawn,-123456.))
        if not near(v,a):raise ValueError('attribute and blackboard value disagree')
        fp=self.typed_float(p,v,missing)
        if not near(v,self.decoded_float(p,pawn)):raise ValueError('native parameter float disagrees with blackboard value')
        return v,fp,p
    def write(self,name,pawn,p):
        r=self.calls['SetBlackboardParam'](self.key(name),self.check(p,PARAM),pawn)
        if type(r) is not tuple or len(r)!=3 or r[0] is not Ellipsis or self.check(r[1],ENTRY).Name!=name or self.fingerprint(self.check(r[2],PARAM))!=self.fingerprint(p):raise ValueError('native setter response uncertain')

class Trial:
    def __init__(self,mode,scale,binding,context,weak,clock,thread,report,permission):
        if mode not in TARGETS or type(scale) not in (int,float) or not math.isfinite(scale) or not 1<scale<=10:raise ValueError('choose a reward multiplier above 1x')
        self.mode,self.name,self.scale=mode,TARGETS[mode],scale
        self.binding,self.context,self.weak,self.clock,self.thread,self.report,self.permission=binding,context,weak,clock,thread,report,permission
        self.record=None;self.fault=False;self.busy=False;self.phase='idle';self.stop_requested=False;self.due=0.;self.owned=False
    def scope(self):
        pc,pawn,state,ok=self.context()
        if ok is not True or pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name() or identity(pc.Pawn)!=identity(pawn):raise ValueError('original local character required')
        struct(pawn,'blackboard',ENGINE+'GbxBlackboard')
        objs=(pc,pawn,state);ids=tuple(identity(o) for o in objs)
        if len(set(ids))!=3:raise ValueError('ambiguous owner identity')
        if self.record:
            refs,oldids,tid,_=self.record
            if ids!=oldids or self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)):raise ValueError('original local scope lost')
        return objs
    def observe(self):
        objs=self.scope();pawn=objs[1];b=self.binding
        missing=b.absent_witness(pawn)
        key=b.definition(self.name);v,fp,p=b.read(self.name,pawn,missing)
        # Independent peers only read through the attribute resolver; unresolved peers
        # are allowed, but their actual raw values must not change during our write.
        peers=tuple(b.calls['GetValueOfAttribute'](n,pawn,-123456.) for n in TARGETS.values() if n!=self.name)
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in peers):raise ValueError('peer value unavailable')
        return objs,key,missing,v,fp,p,peers
    def stable(self):
        a,b=self.observe(),self.observe()
        if tuple(identity(o) for o in a[0])!=tuple(identity(o) for o in b[0]) or a[1:5]!=b[1:5] or a[6]!=b[6]:raise ValueError('reward preflight changed')
        return b
    def begin(self):
        if self.record or self.fault or self.phase!='idle':return False
        try:
            objs,key,missing,v,fp,p,peers=self.stable();self.target=number(v*self.scale)
            if self.permission() is not True or near(v,self.target):raise ValueError('activation not permitted or ineffective target')
            self.base=(key,missing,v,fp,p,peers);self.record=(tuple(self.weak(o) for o in objs),tuple(identity(o) for o in objs),self.thread(),self.clock()+30.);self.phase='armed'
            self.report('EXPERIMENT: '+self.name+' armed for 30 seconds; earned rewards are not reversed.');return True
        except Exception as e:self.report('HOLD: native reward '+str(e)[:140]);return False
    def stop(self,reason):
        if self.record:self.stop_requested=True;self.report('STOP PENDING: native reward '+reason)
    def matches(self,s,v,fp):return s[1:3]==self.base[:2] and near(s[3],v) and s[4]==fp
    def cleanup(self,s):
        if not self.matches(s,self.target,self.target_fp):raise ValueError('owned reward value changed; no overwrite')
        self.owned=False # never retry setter after dispatch
        self.binding.write(self.name,s[0][1],self.base[4])
        now=self.stable()
        if not self.matches(now,self.base[2],self.base[3]) or now[6]!=self.base[5]:raise ValueError('original reward or peer restoration unverified')
        self.phase='verify';self.due=self.clock()+.2
    def tick(self,permitted):
        if not self.record or self.busy:return
        self.busy=True
        try:
            if self.phase=='armed' and (not permitted or self.stop_requested or self.clock()>=self.record[3] or self.permission() is not True):self.record=None;self.phase='done';return
            if self.phase=='active' and permitted and not self.stop_requested and self.clock()<min(self.due,self.record[3]) and self.permission() is True:return
            if self.phase=='verify' and self.clock()<self.due:return
            s=self.stable()
            if self.phase=='armed':
                if not self.matches(s,self.base[2],self.base[3]) or s[6]!=self.base[5] or self.permission() is not True:raise ValueError('armed reward baseline changed')
                p=self.binding.make_float(self.target);self.target_fp=self.binding.typed_float(p,self.target,self.base[1])
                if not near(self.target,self.binding.decoded_float(p,s[0][1])):raise ValueError('native target float conversion disagrees')
                s=self.stable()
                if (not self.matches(s,self.base[2],self.base[3]) or s[6]!=self.base[5] or self.stop_requested
                        or self.clock()>=self.record[3] or self.permission() is not True):raise ValueError('reward scope or permission changed during target construction')
                self.phase='active';self.owned=True
                self.binding.write(self.name,s[0][1],p);s=self.stable()
                if not self.matches(s,self.target,self.target_fp) or s[6]!=self.base[5]:raise ValueError('native reward change or peer isolation unverified')
                self.due=self.clock()+.5;self.report('EXPERIMENT: '+self.name+' value changed; actual earned reward unverified.')
                if self.stop_requested or self.permission() is not True:self.cleanup(s)
            elif self.phase=='active':
                if not self.matches(s,self.target,self.target_fp) or s[6]!=self.base[5]:raise ValueError('reward or peer drift')
                if not permitted or self.stop_requested or self.clock()>=self.record[3] or self.permission() is not True:self.cleanup(s)
                else:self.due=self.clock()+.5
            elif self.phase=='verify':
                if not self.matches(s,self.base[2],self.base[3]) or s[6]!=self.base[5]:raise ValueError('delayed reward restoration unverified')
                self.record=None;self.phase='done';self.report('EXPERIMENT: native reward baseline restored; actual earned reward unverified.')
        except Exception as e:
            if self.phase=='armed':self.record=None;self.phase='done';self.report('HOLD: '+str(e)[:120]);return
            if self.owned:
                try:self.cleanup(self.stable())
                except Exception:pass
            self.fault=True;self.record=None;self.phase='fault';self.report('FAULT: native reward '+str(e)[:120]+'; exit game, do not travel.')
        finally:self.busy=False
