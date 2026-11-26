"""Offline integration candidate: exact native metadata binding, no invocation.
Not included in the SDKMOD. Historical declaration names are candidates only;
no tag, rate, resource, ID sentinel or SDK marshalling assumptions are made.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Param:
    name: str
    kind: str
    target: str | None = None

ACTOR = Param('Context','ZObjectProperty','/Script/Engine.Actor')
RATE = Param('RegenRate','ZStructProperty','/Script/GbxEngine.GbxAttributeInit')
TAGS = Param('HealthTags','ZStructProperty','/Script/GameplayTags.GameplayTagContainer')
DAMAGE = '/Script/GbxGame.DamageStatics:'
SKILL = '/Script/OakGame.GbxSkillComponentFunctions_ActionSkill:'
SIGNATURES = {
    DAMAGE+'StartHealthRegen': (ACTOR,Param('Duration','ZFloatProperty'),RATE,Param('bStopWhenFull','ZBoolProperty'),Param('TickRate','ZFloatProperty'),TAGS,Param('ReturnValue','ZIntProperty')),
    DAMAGE+'StopHealthRegen': (ACTOR,Param('ID','ZIntProperty')),
    DAMAGE+'GetHealthPoolPercent': (ACTOR,Param('layer','ZIntProperty'),Param('ReturnValue','ZFloatProperty')),
}
for name in ('GetCooldown','GetCooldownAsPercent','GetDuration','GetDurationAsPercent'):
    SIGNATURES[SKILL+name] = (Param('target','ZObjectProperty','/Script/OakGame.OakCharacter'),Param('ReturnValue','ZFloatProperty'))


def bind_exact(functions, path):
    """Resolve only allowlisted static declarations; never invoke native code."""
    signature=SIGNATURES[path]
    matches=[f for f in functions if f._path_name()==path]
    if len(matches)!=1: raise ValueError('missing or ambiguous function')
    fn=matches[0]
    props=tuple(fn._properties())
    if fn.NumParams!=len(signature) or len(props)!=len(signature): raise ValueError('parameter count mismatch')
    for p,s in zip(props,signature,strict=True):
        if (str(p.Name),type(p).__name__,p.ArrayDim)!=(s.name,s.kind,1): raise ValueError('parameter mismatch: '+s.name)
        if s.target is not None:
            t=p.Struct if s.kind=='ZStructProperty' else p.PropertyClass
            if t._path_name()!=s.target: raise ValueError('parameter target mismatch: '+s.name)
    owner=fn.Outer
    if owner._path_name()!=path.rsplit(':',1)[0]: raise ValueError('function owner mismatch')
    bound=getattr(owner.ClassDefaultObject,path.rsplit(':',1)[1])
    if bound.func._path_name()!=path: raise ValueError('bound function mismatch')
    return bound


def recovery_bindings(functions):
    """Atomic start/stop/health read binding; still requires argument admission."""
    functions=tuple(functions)
    return tuple(bind_exact(functions,DAMAGE+n) for n in ('StartHealthRegen','StopHealthRegen','GetHealthPoolPercent'))
