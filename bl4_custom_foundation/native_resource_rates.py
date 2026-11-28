"""Experimental native resource-rate modifiers; no refill pulses or shared writes.

Manual opt-in candidate; exact runtime definition, owner, and modifier ABI
must all be resolved before any dispatch. One handle per bounded manual trial; never replay an add
or remove after uncertain native dispatch. See SOURCES.md for provenance.
"""
import math
from .gameplay_fields import identity
from .health_pulse import numeric, enum_name
from .weapon_rates import prop
from .double_jump import struct

LIB='/Script/GbxEngine.GbxAttributeBlueprintLibrary:'
DEF='/Script/GbxEngine.GbxAttributeDef'
HANDLE='/Script/GbxEngine.GbxAttributeModifierHandle'
MOD_ENUM='/Script/GbxCore.EGbxAttributeModifierType'
RESULT_ENUM='/Script/GbxEngine.EGbxAttributeModifierActionExecOutput'
VALUE='/Script/GbxEngine.PropertyValueResolver'
PARSED='/Script/GbxCore.ParsedProperty'
HEALTH_CONTEXT='/Script/GbxGame.GameResourcePoolContextResolver'
SKILL_CONTEXT='/Script/OakGame.OakActionSkillResourcePoolResolver'
LUCK_CONTEXT='/Script/GbxGame.GbxPlayerControllerContextResolver'
LUCK_VALUE='/Script/OakGame.LuckCategoryValueResolver'
LUCK_MODE='gear_luck'
# Name, native property, exact context, selector, modifier, bounded experiment.
TARGETS={
    LUCK_MODE: ('att_luck_gear','Category',LUCK_CONTEXT,'LuckCategory_Gear','ScaleMultiply',2.),
    'health': ('health_resource_passive_pct_regen','PassivePercentRegenerationRate',HEALTH_CONTEXT,'Health','PostAdd',.001),
    'missing_health': ('health_resource_passive_missing_pct_regen','PassiveMissingPercentRegenerationRate',HEALTH_CONTEXT,'Health','PostAdd',.001),
    'shield_idle_rate': ('shield_resource_idle_regen_rate','OnIdleRegenerationRate',HEALTH_CONTEXT,'Shield','ScaleMultiply',2.),
    'shield_idle_delay': ('shield_resource_idle_regen_delay','OnIdleRegenerationDelay',HEALTH_CONTEXT,'Shield','ScaleMultiply',.5),
    'cooldown': ('Att_PlayerShared_ActionSkill_Pool_Cooldown_Rate','ActiveRegenerationRate',SKILL_CONTEXT,'Cooldown','ScaleMultiply',2.),
    'duration': ('Att_PlayerShared_ActionSkill_Pool_Duration_Rate','ConsumptionRate',SKILL_CONTEXT,'Duration','ScaleMultiply',.5),
}
HEALTH_MODES=frozenset(('health','missing_health'))
SHIELD_MODES=frozenset(('shield_idle_rate','shield_idle_delay'))
RESOURCE_MODES=HEALTH_MODES | SHIELD_MODES
SPECS={
    'GetValueOfAttribute':(('AttributeDef','ZNameProperty'),('ContextSource','ZObjectProperty'),('DefaultValue','ZFloatProperty'),('ReturnValue','ZFloatProperty')),
    'AddModifierToGbxAttribute':(('attribute','ZGbxDefPtrProperty'),('ContextSource','ZObjectProperty'),('ModifierType','ZEnumProperty'),('modifiervalue','ZFloatProperty'),('bAutoRefresh','ZBoolProperty'),('ModifierActionResult','ZEnumProperty'),('ReturnValue','ZStructProperty')),
    'RemoveAttributeModifier':(('ModifierHandle','ZStructProperty'),('ReturnValue','ZBoolProperty')),
}


class EligibilityLost(ValueError):
    """Authoritative context returned a false eligibility flag; not an add failure."""


def trial_amount(mode,selection=None):
    """Health selection scales the .001 additive increment, skill selection is a speed/duration factor."""
    if mode not in TARGETS:raise ValueError('unknown native rate trial')
    if selection is None:return TARGETS[mode][-1]
    if mode==LUCK_MODE:
        if type(selection) not in (int,float) or not math.isfinite(selection) or not 1<selection<=10:
            raise ValueError('choose gear luck above 1x through 10x')
        return selection
    if mode in SHIELD_MODES:
        if type(selection) not in (int,float) or not math.isfinite(selection) or not .5<=selection<=3 or selection==1:
            raise ValueError('choose .5–3x shield speed other than 1x')
        return selection if mode=='shield_idle_rate' else 1./selection
    if type(selection) not in (int,float) or not math.isfinite(selection) or not 1<=selection<=5 or (mode not in HEALTH_MODES and selection==1):
        raise ValueError('select 1–5x health increment or above 1x skill factor')
    return .001*selection if mode in HEALTH_MODES else selection if mode=='cooldown' else 1./selection


def close(a,b):
    return math.isclose(a,b,rel_tol=1e-5,abs_tol=1e-7)


def enum_member(desc, path, name):
    if desc.Enum._path_name()!=path:raise ValueError('unexpected enum descriptor')
    typ=desc.Enum._as_py()
    v=getattr(typ,name)
    if enum_name(v)!=name:raise ValueError('unexpected enum member')
    return v


class NativeBinding:
    def __init__(self, functions, existing, def_type, handle_wrapper):
        self.def_type=def_type;self.handle_wrapper=handle_wrapper
        self.calls={};self.descriptors={}
        for name,sig in SPECS.items():
            matches=[f for f in functions if f._path_name()==LIB+name]
            if len(matches)!=1:raise ValueError('native rate API missing/ambiguous: '+name)
            fn=matches[0];ps=tuple(fn._properties())
            if fn.Outer._path_name()!=LIB[:-1] or fn.NumParams!=len(sig) or tuple((str(p.Name),type(p).__name__) for p in ps)!=sig or any(p.ArrayDim!=1 for p in ps):
                raise ValueError('native rate signature mismatch')
            if name!='RemoveAttributeModifier' and ps[1].PropertyClass._path_name()!='/Script/CoreUObject.Object':
                raise ValueError('native context type mismatch')
            self.descriptors[name]=ps;self.calls[name]=existing(functions,LIB+name,sig)
        a=self.descriptors['AddModifierToGbxAttribute'];r=self.descriptors['RemoveAttributeModifier']
        if a[0].Struct._path_name()!=DEF or a[6].Struct._path_name()!=HANDLE or r[0].Struct._path_name()!=HANDLE or identity(a[6].Struct)!=identity(r[0].Struct):
            raise ValueError('native attribute or handle type mismatch')
        self.attr_type=a[0].Struct;self.handle_type=a[6].Struct
        self.mods={n:enum_member(a[2],MOD_ENUM,n) for n in ('PostAdd','ScaleMultiply')}
        self.success=enum_member(a[5],RESULT_ENUM,'Success');self.failure=enum_member(a[5],RESULT_ENUM,'Failure')

    def definition(self,mode):
        name,field,ctx,selector,_,_=TARGETS[mode]
        d=self.def_type(name,self.attr_type,True)
        if type(d) is not self.def_type or d._name!=name or d._type._path_name()!=DEF or identity(d._type)!=identity(self.attr_type):
            raise ValueError('native attribute definition unavailable')
        # Access only known reflected fields of a resolved FGbxDefPtr. No definition writes.
        for key in ('Context','Value'):prop(d._type,key,'ZGbxInlineStructProperty')
        c,v=d.Context,d.Value
        if c._type._path_name()!=ctx or v._type._path_name()!=(LUCK_VALUE if mode==LUCK_MODE else VALUE):
            raise ValueError('unexpected native resolver kind')
        if mode==LUCK_MODE:
            from .luck_categories import DEFINITION,CATEGORY_ENUM,MODIFIER_ENUM
            cp=prop(v._type,'Category','ZGbxDefPtrProperty');cat=v.Category
            if (cp.Struct._path_name()!=DEFINITION or type(cat) is not self.def_type or cat._name!=selector
                    or cat._type._path_name()!=DEFINITION or identity(cat._type)!=identity(cp.Struct)):
                raise ValueError('exact gear luck category definition required')
            for member,path in (('CategoryType',CATEGORY_ENUM),('ModifierType',MODIFIER_ENUM)):
                if prop(cat._type,member,'ZEnumProperty').Enum._path_name()!=path:
                    raise ValueError('unexpected gear luck enum')
            if enum_name(cat.CategoryType)!='ModifiableAttribute' or enum_name(cat.ModifierType)!='ScaleMultiply':
                raise ValueError('gear luck must advertise a multiplicative modifiable category')
            return d,(identity(d),identity(d._type),identity(c._type),identity(v._type),selector,identity(cat))
        if mode in RESOURCE_MODES:
            resource_prop=prop(c._type,'ResourceDef','ZGameDataHandleProperty')
            resource=c.ResourceDef
            if resource._name!=selector or type(resource._type_handle) is not int or resource._type_handle<=0 or resource._type_handle!=resource_prop.TypeHandle:
                raise ValueError('unexpected native resource identity')
            context_key=(resource._name,resource._type_handle,identity(resource))
        else:
            p=prop(c._type,'PoolType','ZEnumProperty')
            if p.Enum._path_name()!='/Script/OakGame.EOakActionSkillResourcePoolType' or enum_name(c.PoolType)!=selector:
                raise ValueError('unexpected action skill resource selector')
            context_key=(selector,)
        prop(v._type,'PropertySupportsModifierRemoval','ZBoolProperty')
        prop(v._type,'ResolvedType','ZEnumProperty')
        if v.PropertySupportsModifierRemoval is not True or enum_name(v.ResolvedType)!='Float':
            raise ValueError('native property does not advertise removable float modifiers')
        parsed=struct(v,'Property',PARSED)
        prop(parsed._type,'PropertyPath','ZStrProperty');prop(parsed._type,'ParsedPathLength','ZUInt32Property')
        fields=[p for p in parsed._type._properties() if str(p.Name)=='ParsedPath']
        if len(fields)!=1 or type(fields[0]).__name__!='ZStructProperty' or fields[0].ArrayDim!=5 or fields[0].Struct._path_name()!='/Script/GbxCore.ParsedPropertyPathElement':
            raise ValueError('unexpected native parsed property schema')
        if str(parsed.PropertyPath)!=field or type(parsed.ParsedPathLength) is not int or parsed.ParsedPathLength!=1:
            raise ValueError('native path is not the exact rate property')
        element=parsed.ParsedPath[0]
        if identity(element._type)!=identity(fields[0].Struct):raise ValueError('native parsed element mismatch')
        prop(element._type,'PropertyName','ZNameProperty');prop(element._type,'bUsesArrayIndex','ZBoolProperty')
        if str(element.PropertyName)!=field or element.bUsesArrayIndex is not False:raise ValueError('native parsed path disagrees with rate property')
        return d,(identity(d),identity(d._type),identity(c._type),identity(v._type),field,context_key)

    def read(self,mode,pawn):
        value=numeric(self.calls['GetValueOfAttribute'](TARGETS[mode][0],pawn,-123456.))
        if not (0<=value<=1e4 if mode not in HEALTH_MODES else 0<=value<=.1):
            raise ValueError('native rate unresolved or outside conservative range')
        if mode not in HEALTH_MODES and value<=0:raise ValueError('positive native skill rate required')
        return value

    def valid_handle(self,h):
        return type(h) is self.handle_wrapper and h._type._path_name()==HANDLE and identity(h._type)==identity(self.handle_type)

    def add(self,mode,d,pawn,selection=None):
        modifier=TARGETS[mode][-2];amount=trial_amount(mode,selection)
        result=self.calls['AddModifierToGbxAttribute'](d,pawn,self.mods[modifier],amount,True,self.failure)
        # The SDK returns return value followed by *all* out parameters,
        # including the const-ref definition, not merely the success enum.
        if type(result) is not tuple or len(result)!=3:raise ValueError('native add return shape uncertain')
        h,echo,status=result
        if type(status) is not type(self.success) or status!=self.success or not self.valid_handle(h):
            raise ValueError('native add did not return an exact successful handle')
        # The valid handle must not be discarded if echo validation fails.
        echo_ok=False
        try:echo_ok=(type(echo) is self.def_type and echo._name==d._name and identity(echo._type)==identity(d._type) and identity(echo)==identity(d))
        except Exception:pass
        return h,echo_ok

    def remove(self,h):
        if not self.valid_handle(h):raise ValueError('unexpected native handle wrapper')
        result=self.calls['RemoveAttributeModifier'](h)
        if type(result) is not tuple or len(result)!=2 or result[0] is not True or not self.valid_handle(result[1]):
            raise ValueError('native removal result uncertain')


class NativeRateTrial:
    """Bounded one-add/one-remove controller using a positively resolved local target.

    resolve() must provide the original local objects, immutable pool identity,
    and exact validated native definition. It may not mutate the game. Caller
    must run tick on the existing verified game hook; no scheduling here.
    """
    def __init__(self,mode,binding,resolve,weak,clock,thread,report,can_add,cleanup_key=lambda key:key,selection=None,continuous=False):
        if mode not in TARGETS:raise ValueError('unknown native rate trial')
        self.mode,self.binding,self.resolve,self.weak=mode,binding,resolve,weak
        self.clock,self.thread,self.report,self.can_add=clock,thread,report,can_add
        self.cleanup_key=cleanup_key;self.selection=selection
        if type(continuous) is not bool:raise ValueError('invalid native rate lifetime')
        if mode in SHIELD_MODES | {'missing_health',LUCK_MODE} and continuous:
            raise ValueError('native rate is isolated manual only')
        self.continuous=continuous
        trial_amount(mode,selection)
        self.record=None;self.fault=False;self.busy=False;self.used=False;self.stop_requested=False
        self.handle=None;self.phase='idle';self.baseline=None;self.expected=None;self.anomaly=False;self.due=0.
        self.next_selection=None

    def dispatch_target(self,cleanup=False,restore_verify=False):
        # Only removal of an already-owned handle may use the original scope
        # after eligibility loss. Verification still requires the full witness,
        # including peer readbacks and maxima; it does not grant add permission.
        resolver=(getattr(self.resolve,'original',self.resolve) if cleanup else
                  getattr(self.resolve,'restored',self.resolve) if restore_verify else self.resolve)
        objs,key,d=resolver()
        ids=tuple(identity(o) for o in objs)
        if len(ids)<3 or len(set(ids))!=len(ids):raise ValueError('ambiguous local owner identity')
        if self.record is not None:
            refs,oldids,oldkey,tid,_=self.record
            if ids!=oldids or (self.cleanup_key(key)!=self.cleanup_key(oldkey) if cleanup else key!=oldkey) or self.thread()!=tid or any(r() is None or identity(r())!=i for r,i in zip(refs,ids,strict=True)):
                raise ValueError('original local pool/session changed')
        return objs,key,d

    def snapshot(self,restore_verify=False):
        objs,key,d=self.dispatch_target(restore_verify=restore_verify)
        value=self.binding.read(self.mode,objs[0] if self.mode==LUCK_MODE else objs[1])
        return objs,key,d,value

    def stable_snapshot(self,restore_verify=False):
        a=self.snapshot(restore_verify);b=self.snapshot(restore_verify)
        if tuple(identity(x) for x in a[0])!=tuple(identity(x) for x in b[0]) or a[1]!=b[1] or not close(a[3],b[3]):
            raise ValueError('local resource identity or rate changed during preflight')
        return b

    def target_value(self,base):
        modifier=TARGETS[self.mode][-2];amount=trial_amount(self.mode,self.selection)
        expected=base+amount if modifier=='PostAdd' else base*amount
        if not 0<expected<=(.1 if self.mode in HEALTH_MODES else 1e4):raise ValueError('native trial target outside conservative bound')
        return expected

    def begin(self):
        if self.record or self.fault or self.busy or self.used:return False
        try:
            objs,key,_,base=self.stable_snapshot()
            if not self.permission():raise ValueError('local activation permission unavailable')
            self.target_value(base)
            self.record=(tuple(self.weak(o) for o in objs),tuple(identity(o) for o in objs),key,self.thread(),self.clock()+(30. if self.mode==LUCK_MODE else 10.) if not self.continuous else float('inf'))
            self.baseline=base;self.phase='armed'
        except Exception as e:self.report('HOLD: native rate '+str(e)[:120]);return False
        self.report('EXPERIMENT: native '+self.mode+' rate armed; no refill pulses.');return True

    def permission(self):
        try:return self.can_add() is True
        except Exception:return False

    def stop(self,reason):
        if self.record is None:return
        self.stop_requested=True
        self.report('STOP PENDING: native rate; wait for original game hook. '+reason)

    def fail(self,reason):
        self.fault=True;self.record=None;self.phase='fault'
        self.report('FAULT: native rate '+reason+'; exit game, do not travel.')

    def cleanup(self):
        if self.handle is None:raise ValueError('no exact original modifier handle')
        self.dispatch_target(cleanup=True)
        h=self.handle;self.handle=None # never retry even if native raises
        self.binding.remove(h)
        _,_,_,value=self.stable_snapshot(restore_verify=True)
        if not close(value,self.baseline):raise ValueError('immediate removal did not restore baseline')
        self.phase='verify';self.verify_at=self.clock()+.15

    def rearm_verified(self, original, selection):
        """Only a saved explicit edit, following successful delayed cleanup, may rearm.
        Revalidate the original weak scope and captured baseline; never follow a replacement pool.
        """
        if not self.continuous or self.phase!='done' or self.record is not None or self.handle is not None or self.fault or self.anomaly:
            return False
        try:
            trial_amount(self.mode,selection)
            self.selection=selection
            self.record=original
            _,_,_,value=self.stable_snapshot()
            if not close(value,self.baseline) or not self.permission():
                raise ValueError('original rate or permission changed after restoration')
            self.target_value(value)
        except Exception as exc:
            self.record=None
            self.report('HOLD: native rate update '+str(exc)[:100])
            return False
        self.used=False;self.stop_requested=False;self.phase='armed';self.expected=None
        self.report('EXPERIMENT: edited native rate armed after verified restoration.')
        return True

    def tick(self,permitted):
        if self.record is None or self.busy:return
        self.busy=True
        try:
            _,_,_,tid,end=self.record
            if self.thread()!=tid:
                if self.handle is None and self.phase=='armed':self.record=None;return
                raise ValueError('original game hook thread unavailable')
            if self.phase=='verify':
                if self.clock()<self.verify_at:return
                _,_,_,value=self.stable_snapshot(restore_verify=True)
                if not close(value,self.baseline):raise ValueError('delayed removal readback differs from baseline')
                if self.anomaly:raise ValueError('unexpected add response; original value restored')
                self.record=None;self.phase='done';self.report('EXPERIMENT: native rate baseline restored immediately and on delayed readback; gameplay effect unverified.');return
            if self.phase=='active':
                if not permitted or self.stop_requested or self.clock()>=end or not self.permission():
                    self.cleanup();return
                if self.clock()<self.due:return
                self.due=self.clock()+.25
                _,_,_,value=self.stable_snapshot()
                if not close(value,self.expected):
                    self.anomaly=True;self.cleanup()
                return
            if not permitted or self.stop_requested or self.clock()>=end:
                self.record=None;self.phase='idle';return
            try:
                objs,_,d,value=self.stable_snapshot()
                objs,_,d=self.dispatch_target()
                if not close(value,self.baseline) or self.stop_requested or self.clock()>=end or not self.permission():raise ValueError('armed native rate or permission changed')
            except Exception as e:
                self.record=None;self.phase='idle';self.report('HOLD: native rate '+str(e)[:120]);return
            self.expected=self.target_value(value)
            self.used=True;self.phase='active';self.due=self.clock()+.25
            self.handle,echo_ok=self.binding.add(self.mode,d,objs[0] if self.mode==LUCK_MODE else objs[1],self.selection)
            if not echo_ok:self.anomaly=True
            _,_,_,observed=self.stable_snapshot()
            if not echo_ok or not close(observed,self.expected):
                self.anomaly=True;self.cleanup();return
            self.report('EXPERIMENT: native '+self.mode+' rate readback changed; effect in actual gameplay unverified.')
            if self.stop_requested or not self.permission():self.cleanup()
        except Exception as e:
            # If a read or peer maximum changed, remove only our returned handle
            # if the original pool identity can still be proven. Never repeat a
            # native removal after an uncertain dispatch.
            if self.phase=='active' and self.handle is not None:
                # A false eligibility flag alone is a normal stop. Other
                # failures (including uncertain add responses) stay faulted.
                self.anomaly=self.anomaly or not isinstance(e,EligibilityLost)
                try:self.cleanup()
                except Exception as cleanup_error:self.fail(str(e)[:65]+'; '+str(cleanup_error)[:65])
            else:self.fail(str(e)[:120])
        finally:self.busy=False


def bind_health_readers(functions,existing):
    from .skill_pulse import DIRECT,DIRECT_INTERFACE
    readers=[];kind=None
    for name in ('GetResourcePoolValue','GetResourcePoolPercent'):
        path=DIRECT+name
        matches=[f for f in functions if f._path_name()==path]
        if len(matches)!=1:raise ValueError('native health resource reader missing/ambiguous')
        fn=matches[0];ps=tuple(fn._properties())
        sig=(('owner','ZInterfaceProperty'),('InResource','ZGameDataHandleProperty'),('ReturnValue','ZFloatProperty'))
        if (fn.Outer._path_name()!=DIRECT[:-1] or fn.NumParams!=3 or tuple((str(p.Name),type(p).__name__) for p in ps)!=sig
                or any(p.ArrayDim!=1 for p in ps) or ps[0].InterfaceClass._path_name()!=DIRECT_INTERFACE):
            raise ValueError('native health resource reader signature mismatch')
        h=ps[1].TypeHandle
        if type(h) is not int or not 0<h<=0xffffffff or (kind is not None and kind!=h):raise ValueError('health reader resource type mismatch')
        kind=h;readers.append(existing(functions,path,sig))
    return (*readers,kind)


def local_health_target(pawn,d,ht,readers,cleanup_only=False):
    from .health_pulse import select_health
    from .weapon_rates import nested
    from .skill_pulse import handle
    h,key,ratio=select_health(pawn,ht,'flesh',cleanup_only=cleanup_only)
    health=nested(pawn,'HealthState','OakCharacterHealthState')
    matches=[st for st in health.HealthTypeStates if handle(st.HealthType,ht)==key]
    if len(matches)!=1:raise ValueError('flesh layer identity ambiguous')
    current=numeric(nested(matches[0],'SimpleCurrentHealth','GbxAttributeFloat').Value)
    maximum=numeric(nested(matches[0],'SimpleMaxHealth','GbxAttributeFloat').Value)
    res=d.Context.ResourceDef
    if type(res) is not ht or handle(res,ht)[1]!=readers[2]:raise ValueError('native Health resource type mismatch')
    direct_current=numeric(readers[0](pawn,res));direct_ratio=numeric(readers[1](pawn,res))
    if not (0<=current<=maximum<=1e9 and maximum>0 and 0<=direct_ratio<=1 and close(current,direct_current) and abs(ratio-direct_ratio)<=.005
            and (current>0 and direct_ratio>0 or cleanup_only and current==direct_current==direct_ratio==0)):
        raise ValueError('native Health resource does not agree with original flesh layer')
    return (key,identity(health),identity(matches[0])),handle(res,ht),maximum



def local_shield_target(pawn,d,ht,readers,getter,allow_empty=False,cleanup_only=False):
    from .health_pulse import select_health
    from .weapon_rates import nested
    from .skill_pulse import handle
    from .shield_rates import owned
    shield=getter(pawn);owned(shield,pawn)
    _,key,ratio=select_health(pawn,ht,'shield',cleanup_only=cleanup_only)
    health=nested(pawn,'HealthState','OakCharacterHealthState')
    matches=[st for st in health.HealthTypeStates if handle(st.HealthType,ht)==key]
    if len(matches)!=1:raise ValueError('energy shield layer identity ambiguous')
    current=numeric(nested(matches[0],'SimpleCurrentHealth','GbxAttributeFloat').Value)
    maximum=numeric(nested(matches[0],'SimpleMaxHealth','GbxAttributeFloat').Value)
    res=d.Context.ResourceDef
    if type(res) is not ht or handle(res,ht)[1]!=readers[2]:raise ValueError('native Shield resource type mismatch')
    direct_current=numeric(readers[0](pawn,res));direct_ratio=numeric(readers[1](pawn,res))
    # Zero native reads could also mean an unresolved pool. Admit depletion
    # only after the resolver has independently witnessed the same positive pool.
    if not (0<=current<=maximum<=1e9 and maximum>0 and 0<=direct_ratio<=1 and close(current,direct_current) and abs(ratio-direct_ratio)<=.005
            and (current>0 and direct_ratio>0 or allow_empty is True and current==direct_current==direct_ratio==0)):
        raise ValueError('native Shield resource does not agree with original energy layer')
    if identity(getter(pawn))!=identity(shield):raise ValueError('equipped shield changed during observation')
    return shield,((key,identity(health),identity(matches[0])),handle(res,ht),maximum)

def handle_identity(h):
    return h._name,h._type_handle,identity(h)


def make_local_resolver(mode,binding,context,ht,health_readers=None,skill_reader=None,shield_getter=None):
    """Independently witness native pool ownership before allowing a modifier.

    Existing Health layer or action skill readers are never used to refill.
    Skill pool maxima are pinned to catch the known erroneous duration MaxValue
    parsed-path mapping; this does not assert actual timing or rate units.
    """
    shield_scope=None
    def check_recovery_eligibility(pawn):
        from .weapon_rates import nested
        health=nested(pawn,'HealthState','OakCharacterHealthState')
        disabled=nested(health,'HealingDisabled','GbxAttributeInteger').Value
        if enum_name(pawn.HealthCondition) not in (None,'Healthy') or health.bCurrentlyDead is True or type(disabled) is int and disabled!=0:
            raise EligibilityLost('native recovery state no longer eligible')
    def resolve(include_peer=True,cleanup_only=False):
        nonlocal shield_scope
        pc,pawn,state,ok=context()
        if ok is False and not cleanup_only:
            raise EligibilityLost('local native rate eligibility ended')
        if (ok is not True and not (cleanup_only and ok is False)) or pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or 'Default__' in pawn._path_name():
            raise ValueError('eligible local OakCharacter required')
        d,def_key=binding.definition(mode)
        if mode==LUCK_MODE:
            from .luck_categories import snapshot
            if identity(pc.Pawn)!=identity(pawn):raise ValueError('local luck controller mismatch')
            rows=snapshot(pc,identities=True)
            targets=[row for row in rows if row[0]=='LuckCategory_Gear']
            if len(targets)!=1:raise ValueError('exact gear luck category unavailable')
            row=targets[0]
            if row[1:3]!=('ModifiableAttribute','ScaleMultiply') or row[6]!=def_key[-1]:
                raise ValueError('gear luck definition or modifier mismatch')
            objs=(pc,pawn,state)
            # Array entry and scalar wrapper identity are pinned. No array writes.
            pool_key=(row[5:],)
            if include_peer:
                if not 0<row[3]<=1e4 or not 0<row[4]<=1e4 or not close(binding.read(mode,pc),row[3]):
                    raise ValueError('gear luck native getter disagrees with local category')
                pool_key=(*pool_key,row[4],tuple(r for r in rows if r[0]!=row[0]))
        elif mode in HEALTH_MODES:
            if not cleanup_only:check_recovery_eligibility(pawn)
            objs=(pc,pawn,state);pool_key=local_health_target(pawn,d,ht,health_readers,cleanup_only=cleanup_only)
            if mode=='missing_health' and include_peer:
                # Independent ordinary-rate witness; never edit this peer.
                peer,peer_key=binding.definition('health')
                if identity(peer)==identity(d) or handle_identity(peer.Context.ResourceDef)!=handle_identity(d.Context.ResourceDef):
                    raise ValueError('missing-health and ordinary rate must be distinct on the same Health resource')
                pool_key=(*pool_key,peer_key,binding.read('health',pawn))
        elif mode in SHIELD_MODES:
            if not cleanup_only:check_recovery_eligibility(pawn)
            shield,pool_key=local_shield_target(pawn,d,ht,health_readers,shield_getter,allow_empty=shield_scope is not None,cleanup_only=cleanup_only)
            objs=(pc,pawn,state,shield)
            candidate=(tuple(identity(o) for o in objs),def_key,pool_key[:2])
            if shield_scope is not None and candidate!=shield_scope:
                raise ValueError('original shield witness changed')
        else:
            # The read-only reader can inspect the same authoritative local
            # actor during cleanup even if the player-count gate is now false.
            objs,key,ref,resources,_,_=(skill_reader.resolve(initial=True,refresh=True,cleanup_only=True)
                if cleanup_only and ok is False else skill_reader.resolve(initial=True,refresh=True))
            if tuple(identity(o) for o in objs[:3])!=tuple(identity(o) for o in (pc,pawn,state)):
                raise ValueError('action skill local session changed')
            maxes=tuple(numeric(skill_reader.api[2](ref,h)) for h in resources)
            if len(maxes)!=2 or any(not 0<m<=1e9 for m in maxes):raise ValueError('invalid native skill maximum')
            pool_key=(key,maxes)
        fresh=context()
        if fresh[3] is False and not cleanup_only:
            raise EligibilityLost('local native rate eligibility ended during observation')
        if (fresh[3] is not True and not (cleanup_only and fresh[3] is False)) or tuple(identity(o) for o in fresh[:3])!=tuple(identity(o) for o in objs[:3]):
            raise ValueError('local session changed during rate resolution')
        if mode in RESOURCE_MODES and not cleanup_only:
            check_recovery_eligibility(pawn)
        if mode in SHIELD_MODES and shield_scope is None and not cleanup_only:
            shield_scope=candidate
        return objs,(def_key,pool_key),d
    # The caller must match the original weak owner, pool, and thread before
    # removing its saved handle. Production context still requires local
    # authority and a non-dedicated server; it never returns client authority.
    # Allow the eligibility boolean to be false only for removal/readback.
    # Missing-health peer absence remains a fault during full verification.
    resolve.original=lambda:resolve(include_peer=False,cleanup_only=True)
    resolve.restored=lambda:resolve(cleanup_only=True)
    return resolve


def original_pool_identity(mode,key):
    definition,pool=key
    # Maxima are witnesses, not identities. A handle must still be removable
    # after an anomalous maximum change if the original owner/pool is intact.
    return definition,(pool[:2] if mode in RESOURCE_MODES else pool[0])
