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
GUN_KEY='caused_damage_gun_multiplier'
GUN_MODE='native_gun_damage'
GUN_PEERS=('caused_damage_normal_multiplier','caused_damage_melee_multiplier','caused_damage_gadget_multiplier','caused_damage_action_skill_multiplier','caused_damage_companion_gun_multiplier')
MISSING='BL4Custom_Unused_Reward_Probe_6F79B1'
S='ZStructProperty'; O='ZObjectProperty'; F='ZFloatProperty'; N='ZNameProperty'; T='ZStrProperty'
SPECS={
 'GetBlackboardParamPure':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('OwnerContext',O),('bReportIfMissing','ZBoolProperty'),('ReturnValue',S))),
 'GetBlackboardFloatPure':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('OwnerContext',O),('bReportIfMissing','ZBoolProperty'),('ReturnValue',F))),
 'SetBlackboardFloat':('GbxBlackboardBlueprintLibrary',(('BlackboardKey',S),('Value',F),('OwnerContext',O))),
 'EqualEqual_GbxBlackboardEntryRef':('GbxBlackboardBlueprintLibrary',(('A',S),('B',S),('ReturnValue','ZBoolProperty'))),
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
    targets=TARGETS
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
                    expected=ENTRY if str(p.Name) in ('BlackboardKey','A','B') else PARAM
                    if p.Struct._path_name()!=expected:raise ValueError('unexpected parameter struct')
                    old=self.types.setdefault(expected,p.Struct)
                    if identity(old)!=identity(p.Struct):raise ValueError('parameter type identity differs')
            self.calls[name]=bound(functions,path,sig)
    def check(self,obj,path):
        if type(obj) is not self.wrapper or obj._type._path_name()!=path or identity(obj._type)!=identity(self.types[path]):raise ValueError('unexpected returned native struct')
        return obj
    def key(self,name):
        if name in self.targets.values():return self.resolve_definition(name)[1]
        if name not in (MISSING,MISSING+'_B'):raise ValueError('unsupported reward key')
        prop(self.types[ENTRY],'Name',N)
        result=self.check(self.make(self.types[ENTRY],Name=name),ENTRY)
        if result.Name!=name:raise ValueError('blackboard key mismatch')
        return result
    def resolve_definition(self,name):
        d=self.def_type(name,self.def_struct,True)
        if type(d) is not self.def_type or d._name!=name or identity(d._type)!=identity(self.def_struct):raise ValueError('unresolved reward definition')
        for k in ('Context','Value'):prop(d._type,k,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if c._type._path_name()!=self.context_path(name) or v._type._path_name()!=ENGINE+'GbxBlackboardValueResolver':raise ValueError('not an exact blackboard resolver')
        k=struct(v,'Variable',ENTRY)
        if k.Name!=name:raise ValueError('reward variable mismatch')
        return (identity(d),identity(c._type),identity(v._type),name),self.check(k,ENTRY)
    def context_path(self,name):return ENGINE+'GbxBlackboardOwnerContextResolver'
    def definition(self,name):return self.resolve_definition(name)[0]
    def keys_equal(self,a,b):
        a,b=self.check(a,ENTRY),self.check(b,ENTRY)
        r=self.calls['EqualEqual_GbxBlackboardEntryRef'](a,b)
        if type(r) is not tuple or len(r)!=3 or type(r[0]) is not bool or self.check(r[1],ENTRY).Name!=a.Name or self.check(r[2],ENTRY).Name!=b.Name:raise ValueError('unexpected native key comparison')
        return r[0]
    def echo(self,key,returned):
        return self.check(returned,ENTRY).Name==key.Name and self.keys_equal(key,returned) is True
    def get(self,name,pawn):
        key=self.key(name);r=self.calls['GetBlackboardParamPure'](key,pawn,False)
        if type(r) is not tuple or len(r)!=2 or not self.echo(key,r[1]):raise ValueError('unexpected blackboard read tuple')
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
        keys=tuple(self.key(n) for n in names)
        if self.keys_equal(keys[0],keys[0]) is not True or self.keys_equal(*keys) is not False:raise ValueError('native key equality not calibrated')
        for n in names:
            fp=self.fingerprint(self.get(n,pawn))
            if not all(not x.strip() or re.fullmatch(r'\s*(?:none|invalid|unset|null|empty)\s*',x,re.I) for x in fp):raise ValueError('missing entry representation is ambiguous')
            key=self.key(n);r=self.calls['GetBlackboardFloatPure'](key,pawn,False)
            if type(r) is not tuple or len(r)!=2 or not self.echo(key,r[1]) or type(r[0]) not in (float,int) or r[0]!=0:raise ValueError('missing entry scalar semantics are ambiguous')
            fps.append(fp)
        if fps[0]!=fps[1]:raise ValueError('missing entry witnesses disagree')
        return fps[0]
    def decoded_float(self,p,pawn):
        # Independent native parameter conversion, not Python parsing of diagnostic text.
        r=self.calls['GetGbxParam_Float'](self.check(p,PARAM),pawn)
        if type(r) is not tuple or len(r)!=2 or self.fingerprint(self.check(r[1],PARAM))!=self.fingerprint(p):raise ValueError('native parameter float conversion response uncertain')
        return number(r[0])
    def read(self,name,pawn,missing):
        p=self.get(name,pawn);key=self.key(name);r=self.calls['GetBlackboardFloatPure'](key,pawn,False)
        if type(r) is not tuple or len(r)!=2 or not self.echo(key,r[1]):raise ValueError('unexpected typed float read tuple')
        v=number(r[0]);a=number(self.calls['GetValueOfAttribute'](name,pawn,-123456.))
        if not near(v,a):raise ValueError('attribute and blackboard value disagree')
        fp=self.typed_float(p,v,missing)
        if not near(v,self.decoded_float(p,pawn)):raise ValueError('native parameter float disagrees with blackboard value')
        return v,fp,p
    def write(self,name,pawn,v,expected_definition):
        # Native Float setter avoids copying the opaque FGbxParam into a write call.
        # Never fall back to another setter after an uncertain dispatch.
        definition,key=self.resolve_definition(name)
        if definition!=expected_definition:raise ValueError('reward definition changed before dispatch')
        r=self.calls['SetBlackboardFloat'](key,number(v),pawn)
        if type(r) is not tuple or len(r)!=2 or r[0] is not Ellipsis or not self.echo(key,r[1]):raise ValueError('native float setter response uncertain')

class Trial:
    outcome="actual earned reward unverified"
    armed_note="earned rewards are not reversed"
    targets=TARGETS
    def valid_scale(self,scale):return 1<scale<=10
    def peer_names(self):return tuple(n for n in TARGETS.values() if n!=self.name)
    def __init__(self,mode,scale,binding,context,weak,clock,thread,report,permission):
        if mode not in self.targets or type(scale) not in (int,float) or not math.isfinite(scale) or not self.valid_scale(scale):raise ValueError('choose a reward multiplier above 1x')
        self.mode,self.name,self.scale=mode,self.targets[mode],scale
        self.controller_context=mode=='progress_enemy_xp'
        self.binding,self.context,self.weak,self.clock,self.thread,self.report,self.permission=binding,context,weak,clock,thread,report,permission
        self.record=None;self.fault=False;self.busy=False;self.phase='idle';self.stop_requested=False;self.due=0.;self.owned=False
    def scope(self):
        pc,pawn,state,ok=self.context()
        # Currency trials can clean up their own original board after a false
        # eligibility observation, but must never activate in that state.
        if not self.controller_context and ok is False and self.record and self.phase in ('active','verify'):
            self.stop_requested=True
        elif ok is not True:raise ValueError('original local character required')
        if pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name() or identity(pc.Pawn)!=identity(pawn):raise ValueError('original local character required')
        board=struct(pawn,'blackboard',ENGINE+'GbxBlackboard')
        if not self.controller_context:
            if pc.Class._path_name()!='/Script/OakGame.OakPlayerController' or 'Default__' in pc._path_name():raise ValueError('exact local currency controller required')
            board_key=(identity(board),identity(board._type))
            if getattr(self,'board_key',board_key)!=board_key:raise ValueError('original currency blackboard scope lost')
            self.board_key=board_key
        if self.controller_context and (pc.Class._path_name()!='/Script/OakGame.OakPlayerController' or 'Default__' in pc._path_name()):raise ValueError('exact local XP controller required')
        objs=(pc,pawn,state);ids=tuple(identity(o) for o in objs)
        if len(set(ids))!=3:raise ValueError('ambiguous owner identity')
        if self.record:
            refs,oldids,tid,_=self.record
            if ids!=oldids or self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)):raise ValueError('original local scope lost')
        return objs
    def owner(self,objs):return objs[0] if self.controller_context else objs[1]
    def observe(self):
        objs=self.scope();pawn=objs[1];owner=self.owner(objs);b=self.binding
        missing=b.absent_witness(owner)
        key=b.definition(self.name);v,fp,p=b.read(self.name,owner,missing)
        # Independent peers only read through the attribute resolver; unresolved peers
        # are allowed, but their actual raw values must not change during our write.
        contexts=(owner,pawn) if self.controller_context else (owner,)
        peers=tuple(b.calls['GetValueOfAttribute'](n,c,-123456.) for c in contexts for n in self.peer_names())
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in peers):raise ValueError('peer value unavailable')
        # The controller is a context, not proof of a separate embedded board.
        # Require the existing local pawn's typed entry as an independent witness.
        witness=None
        if self.controller_context:
            pm=b.absent_witness(pawn);pv,pfp,_=b.read(self.name,pawn,pm)
            witness=(pm,pv,pfp)
        return objs,key,missing,v,fp,p,peers,witness
    def stable(self):
        a,b=self.observe(),self.observe()
        if tuple(identity(o) for o in a[0])!=tuple(identity(o) for o in b[0]) or a[1:5]!=b[1:5] or a[6:]!=b[6:]:raise ValueError('reward preflight changed')
        return b
    def begin(self):
        if self.record or self.fault or self.phase!='idle':return False
        try:
            objs,key,missing,v,fp,p,peers,witness=self.stable();self.target=number(v*self.scale)
            if self.controller_context and not self.witness_matches(witness,missing,v,fp):raise ValueError('controller/pawn XP baseline mismatch')
            if self.permission() is not True or near(v,self.target):raise ValueError('activation not permitted or ineffective target')
            self.base=(key,missing,v,fp,p,peers);self.record=(tuple(self.weak(o) for o in objs),tuple(identity(o) for o in objs),self.thread(),self.clock()+30.);self.phase='armed'
            self.report('EXPERIMENT: '+self.name+' armed for 30 seconds; '+self.armed_note+'.');return True
        except Exception as e:self.report('HOLD: native reward '+str(e)[:140]);return False
    def stop(self,reason):
        if self.record:self.stop_requested=True;self.report('STOP PENDING: native reward '+reason)
    @staticmethod
    def witness_matches(w,missing,v,fp):return w is not None and w[0]==missing and near(w[1],v) and w[2]==fp
    def primary_matches(self,s,v,fp):return s[1:3]==self.base[:2] and near(s[3],v) and s[4]==fp
    def matches(self,s,v,fp):
        return self.primary_matches(s,v,fp) and (not self.controller_context or self.witness_matches(s[7],self.base[1],v,fp))
    def cleanup(self,s):
        if not self.primary_matches(s,self.target,self.target_fp):raise ValueError('owned reward value changed; no overwrite')
        if self.controller_context and not (self.witness_matches(s[7],self.base[1],self.target,self.target_fp) or self.witness_matches(s[7],self.base[1],self.base[2],self.base[3])):raise ValueError('foreign pawn XP witness; no overwrite')
        self.owned=False # never retry setter after dispatch
        self.binding.write(self.name,self.owner(s[0]),self.base[2],self.base[0])
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
                if not near(self.target,self.binding.decoded_float(p,self.owner(s[0]))):raise ValueError('native target float conversion disagrees')
                s=self.stable()
                if (not self.matches(s,self.base[2],self.base[3]) or s[6]!=self.base[5] or self.stop_requested
                        or self.clock()>=self.record[3] or self.permission() is not True):raise ValueError('reward scope or permission changed during target construction')
                self.phase='active';self.owned=True
                self.binding.write(self.name,self.owner(s[0]),self.target,self.base[0]);s=self.stable()
                if not self.matches(s,self.target,self.target_fp) or s[6]!=self.base[5]:raise ValueError('native reward change or peer isolation unverified')
                self.due=self.clock()+.5;self.report('EXPERIMENT: '+self.name+' value changed; '+self.outcome+'.')
                if self.stop_requested or self.permission() is not True:self.cleanup(s)
            elif self.phase=='active':
                if not self.matches(s,self.target,self.target_fp) or s[6]!=self.base[5]:raise ValueError('reward or peer drift')
                if not permitted or self.stop_requested or self.clock()>=self.record[3] or self.permission() is not True:self.cleanup(s)
                else:self.due=self.clock()+.5
            elif self.phase=='verify':
                if not self.matches(s,self.base[2],self.base[3]) or s[6]!=self.base[5]:raise ValueError('delayed reward restoration unverified')
                self.record=None;self.phase='done';self.report('EXPERIMENT: native attribute baseline restored; '+self.outcome+'.')
        except Exception as e:
            if self.phase=='armed':self.record=None;self.phase='done';self.report('HOLD: '+str(e)[:120]);return
            if self.owned:
                try:self.cleanup(self.stable())
                except Exception:pass
            self.fault=True;self.record=None;self.phase='fault';self.report('FAULT: native reward '+str(e)[:120]+'; exit game, do not travel.')
        finally:self.busy=False


class GunBinding(Binding):
    """Separate existing actor blackboard entry; never synthesize a missing key."""
    targets={GUN_MODE:GUN_KEY}
    def context_path(self,name):
        if name!=GUN_KEY:raise ValueError('unsupported gun attribute')
        return ENGINE+'ActorContextResolver'


class GunTrial(Trial):
    outcome="actual ordinary gun damage unverified"
    armed_note="only existing local actor gun damage entry targeted"
    targets=GunBinding.targets
    def valid_scale(self,scale):return .5<=scale<=5 and scale!=1
    def peer_names(self):return (*TARGETS.values(),*GUN_PEERS)
    def scope(self):
        # Preserve original owner and embedded board, even if another player
        # joins: no new activation in that case; permit original cleanup only.
        pc,pawn,state,ok=self.context()
        if ok is False and self.phase in ('active','verify') and self.record:
            self.stop_requested=True
        elif ok is not True:raise ValueError('eligible solo gun context required')
        if (pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name()
                or identity(pc.Pawn)!=identity(pawn) or pc.Class._path_name()!='/Script/OakGame.OakPlayerController' or 'Default__' in pc._path_name()):
            raise ValueError('exact local gun owner required')
        board=struct(pawn,'blackboard',ENGINE+'GbxBlackboard')
        board_key=(identity(board),identity(board._type))
        objs=(pc,pawn,state);ids=tuple(identity(o) for o in objs)
        if len(set(ids))!=3:raise ValueError('ambiguous gun owner')
        if self.record:
            refs,oldids,tid,_=self.record
            if ids!=oldids or self.thread()!=tid or board_key!=self.board_key or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)):
                raise ValueError('original gun blackboard scope lost')
        elif getattr(self,'board_key',board_key)!=board_key:raise ValueError('gun blackboard changed during preflight')
        self.board_key=board_key
        return objs


CASH_GENERIC='Att_PickupCash_Multiplier_Generic'
CASH_FORMULA='calc_cash_pickup'
CASH_LEVEL='Att_ActorExperienceLevel'


class CashFormulaConflict(ValueError):
    pass


class CashFormulaBinding(Binding):
    """Alternative existing cash entry, independently witnessed by cash formula.

    The compiled expression is opaque in historical reflection; verify its
    observed numeric result, not a guessed interpretation of native memory.
    """
    targets={'progress_money':CASH_GENERIC}
    formula_peer=TARGETS['progress_money']

    def formula(self,pawn):
        d=self.def_type(CASH_FORMULA,self.def_struct,True)
        if type(d) is not self.def_type or d._name!=CASH_FORMULA or identity(d._type)!=identity(self.def_struct):
            raise ValueError('exact cash formula definition unavailable')
        for k in ('Context','Value'):prop(d._type,k,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if c._type._path_name()!=ENGINE+'ActorContextResolver' or v._type._path_name()!=ENGINE+'GbxExpressionValueResolver':
            raise ValueError('cash formula resolver mismatch')
        e=struct(v,'Expression',ENGINE+'GbxAttributeExpression')
        key=(identity(d),identity(c._type),identity(v._type),identity(e._type))
        read=self.calls['GetValueOfAttribute']
        primary=read(self.formula_peer,pawn,-123456.)
        level=read(CASH_LEVEL,pawn,-123456.)
        actual=read(CASH_FORMULA,pawn,-123456.)
        if any(type(x) in (int,float) and x==-123456. for x in (primary,level,actual)):
            raise ValueError('cash formula input unavailable')
        try:primary=number(primary)
        except ValueError as exc:raise CashFormulaConflict('invalid cash formula peer multiplier') from exc
        if (type(level) not in (int,float) or not math.isfinite(level) or not 1<=level<=1000 or int(level)!=level
                or type(actual) not in (int,float) or not math.isfinite(actual) or not 0<actual<=4e7):
            raise CashFormulaConflict('cash formula or actor level invalid')
        return key,primary,float(level),float(actual)


class CashFormulaTrial(Trial):
    targets=CashFormulaBinding.targets
    outcome='cash formula readback checked; actual pickup award unverified'
    armed_note='existing generic cash entry and formula baseline witnessed; earned rewards are not reversed'
    requires_formula=True

    def observe(self):
        s=super().observe()
        # An unavailable consumer must not prevent restoration of our still
        # positively identified existing entry after dispatch.
        try:witness=self.binding.formula(s[0][1])
        except CashFormulaConflict:witness=('invalid',)
        except Exception:witness=None
        return (*s[:7],witness)

    @staticmethod
    def formula_matches(witness,value,baseline=None):
        return (witness is not None and len(witness)==4 and (baseline is None or witness[:3]==baseline)
                and near(witness[3],4*witness[1]*witness[2]*value))

    def begin(self):
        if self.record or self.fault or self.phase!='idle':return False
        try:
            objs,key,missing,v,fp,p,peers,witness=self.stable()
            self.target=number(v*self.scale)
            if (witness is None and self.requires_formula) or (witness is not None and not self.formula_matches(witness,v)):raise ValueError('existing cash formula does not agree with selected entry')
            if self.permission() is not True or near(v,self.target):raise ValueError('activation not permitted or ineffective target')
            self.formula_base=witness[:3] if witness is not None else None
            self.formula_level=witness[2] if witness is not None else None
            if witness is None:
                self.outcome='cash entry readback checked; formula and actual pickup award unverified'
                self.armed_note='existing primary cash entry witnessed; native formula unavailable; earned rewards are not reversed'
            self.base=(key,missing,v,fp,p,peers)
            self.record=(tuple(self.weak(o) for o in objs),tuple(identity(o) for o in objs),self.thread(),float('inf') if getattr(self,'continuous',False) else self.clock()+30.)
            self.phase='armed'
            self.report('EXPERIMENT: '+self.name+(' armed for this session; ' if getattr(self,'continuous',False) else ' armed for 30 seconds; ')+self.armed_note+'.');return True
        except Exception as e:self.report('HOLD: generic cash '+str(e)[:140]);return False

    def matches(self,s,v,fp):
        if not self.primary_matches(s,v,fp):return False
        if self.formula_base is None:return not self.requires_formula
        witness=s[7]
        # The same player can legitimately level up from normal gameplay. Do
        # not confuse that with foreign modifier drift. No level write, new
        # reward call or multiplier recapture is performed. During admission
        # require the original level; thereafter only a coherent nondecreasing
        # level with the same expression and peer multiplier is accepted.
        if self.phase=='armed':return self.formula_matches(witness,v,self.formula_base)
        if (witness is None or len(witness)!=4 or witness[:2]!=self.formula_base[:2]
                or witness[2]<self.formula_level or not self.formula_matches(witness,v)):
            return False
        self.formula_level=witness[2]
        return True


class CashPrimaryBinding(CashFormulaBinding):
    targets={'progress_money':TARGETS['progress_money']}
    formula_peer=CASH_GENERIC


class CashPrimaryTrial(CashFormulaTrial):
    """Preserve the original primary entry path if formula read is unavailable.

    When available, require actual expression agreement, including after
    restoration. A contradictory formula is not silently ignored.
    """
    targets=CashPrimaryBinding.targets
    requires_formula=False
    armed_note='existing primary cash entry and formula baseline witnessed; earned rewards are not reversed'
    def peer_names(self):return (*super().peer_names(),CASH_GENERIC)


def choose_cash_trial(primary,alternative):
    """Only use the alternative after a no-dispatch primary preflight HOLD."""
    if primary.begin() or primary.record is not None or primary.fault or primary.phase!='idle' or primary.owned:
        return primary
    lane=alternative()
    lane.begin()
    return lane


class SessionCashMixin:
    """Opt-in session lease; only a witnessed native cash expression is admitted."""
    requires_formula=True
    continuous=True

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.selection=self.scale
        self.next_selection=None

    def rearm_verified(self,original,selection):
        # A changed selection restores first. Explicit off/on is required to
        # re-capture the scope; never silently follow a new character/board.
        return False


class SessionCashPrimary(SessionCashMixin,CashPrimaryTrial):
    pass


class SessionCashGeneric(SessionCashMixin,CashFormulaTrial):
    pass


MELEE_MODE='native_melee_damage'
MELEE_KEY='caused_damage_melee_attack_multiplier'
MELEE_PEER='caused_damage_melee_multiplier'
MELEE_FORMULA='calc_caused_damage_melee_attack_multiplier'


class MeleeBinding(GunBinding):
    """Existing actor melee-attack entry, with independent expression witness."""
    targets={MELEE_MODE:MELEE_KEY}
    def context_path(self,name):
        if name!=MELEE_KEY:raise ValueError('unsupported melee attribute')
        return ENGINE+'ActorContextResolver'

    def formula(self,pawn):
        d=self.def_type(MELEE_FORMULA,self.def_struct,True)
        if type(d) is not self.def_type or d._name!=MELEE_FORMULA or identity(d._type)!=identity(self.def_struct):
            raise ValueError('exact melee formula unavailable')
        for k in ('Context','Value'):prop(d._type,k,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if c._type._path_name()!=ENGINE+'ActorContextResolver' or v._type._path_name()!=ENGINE+'GbxExpressionValueResolver':
            raise ValueError('melee formula resolver mismatch')
        e=struct(v,'Expression',ENGINE+'GbxAttributeExpression')
        key=(identity(d),identity(c._type),identity(v._type),identity(e._type))
        read=self.calls['GetValueOfAttribute']
        return key,number(read(MELEE_PEER,pawn,-123456.)),number(read(MELEE_FORMULA,pawn,-123456.))


class MeleeTrial(GunTrial):
    targets=MeleeBinding.targets
    outcome='melee expression readback checked; actual melee hit damage unverified'
    armed_note='existing local melee attack entry and independent expression witnessed'

    def peer_names(self):return (*super().peer_names(),GUN_KEY)

    def observe(self):
        s=super().observe()
        # Missing formula must not prevent cleanup of an identified owned entry.
        try:w=self.binding.formula(s[0][1])
        except Exception:w=None
        return (*s[:7],w)

    @staticmethod
    def formula_matches(w,value,baseline=None):
        return (w is not None and (baseline is None or w[:2]==baseline)
                and near(w[2],w[1]+value-1.))

    def begin(self):
        if self.record or self.fault or self.phase!='idle':return False
        try:
            objs,key,missing,v,fp,p,peers,w=self.stable()
            self.target=number(v*self.scale)
            if not self.formula_matches(w,v) or not 0<w[1]+self.target-1.<=100:
                raise ValueError('melee formula baseline or target invalid')
            if self.permission() is not True or near(v,self.target):raise ValueError('activation not permitted or ineffective target')
            self.formula_base=w[:2]
            self.base=(key,missing,v,fp,p,peers)
            self.record=(tuple(self.weak(o) for o in objs),tuple(identity(o) for o in objs),self.thread(),self.clock()+30.)
            self.phase='armed'
            self.report('EXPERIMENT: '+self.name+' armed for 30 seconds; '+self.armed_note+'.');return True
        except Exception as e:self.report('HOLD: melee '+str(e)[:140]);return False

    def matches(self,s,v,fp):
        return self.primary_matches(s,v,fp) and self.formula_matches(s[7],v,self.formula_base)
