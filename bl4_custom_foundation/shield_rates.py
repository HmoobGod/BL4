"""Exact equipped energy shield instance, not a shared shield definition or pool edit."""
from .gameplay_fields import identity, pair
from .weapon_rates import nested, prop
from .health_pulse import enum_name
KEYS = frozenset(('shield_regen_rate','shield_regen_delay'))
PATH='/Script/OakGame.OakInventoryStatics:GetShield'
SHIELD='/Script/OakGame.Shield'

def bind(functions, existing):
    sig=(('ShieldUser','ZObjectProperty'),('ReturnValue','ZObjectProperty'))
    found=[f for f in functions if f._path_name()==PATH]
    if len(found)!=1:raise ValueError('unique shield getter unavailable')
    f=found[0]; ps=tuple(f._properties())
    if len(ps)!=2 or any(p.ArrayDim!=1 for p in ps) or tuple(p.PropertyClass._path_name() for p in ps)!=('/Script/Engine.Actor',SHIELD):
        raise ValueError('shield getter descriptor mismatch')
    return existing(functions,PATH,sig)

def member(shield,name,kind,target=None):
    b=getattr(shield,name); f=b.func; ps=tuple(f._properties())
    if f._path_name()!=SHIELD+':'+name or f.NumParams!=1 or len(ps)!=1 or str(ps[0].Name)!='ReturnValue' or type(ps[0]).__name__!=kind or ps[0].ArrayDim!=1:
        raise ValueError('shield member signature mismatch')
    if target and ps[0].Enum._path_name()!=target:raise ValueError('shield enum mismatch')
    return b

def owned(shield,pawn):
    if shield is None or shield.Class._path_name()!=SHIELD or 'Default__' in shield._path_name() or shield.HasAuthority() is not True or shield.IsActorBeingDestroyed() is not False:
        raise ValueError('live authoritative shield unavailable')
    d=prop(shield.Class,'OwningCharacter','ZObjectProperty')
    if d.PropertyClass._path_name()!='/Script/OakGame.OakCharacter' or identity(shield.OwningCharacter)!=identity(pawn):raise ValueError('shield owner mismatch')
    if shield.Owner is not None and identity(shield.Owner)!=identity(pawn):raise ValueError('shield actor owner mismatch')
    if enum_name(member(shield,'K2_GetHealthSystem','ZEnumProperty','/Script/OakGame.EShieldHealthSystem')())!='Energy':raise ValueError('ordinary energy shield required')

def fields(shield,key):
    return pair(nested(shield,'RegenRate' if key=='shield_regen_rate' else 'RegenDelay','GbxAttributeFloat'))

def capture(pawn,key,weak,getter):
    shield=getter(pawn);owned(shield,pawn)
    values=fields(shield,key)
    validate_readback(shield,key,values[0][3])
    return (weak(shield),identity(shield),key,getter)

def resolve(pawn,scope):
    ref,token,key,getter=scope;shield=ref()
    if shield is None or identity(shield)!=token:raise ValueError('original shield lost')
    owned(shield,pawn)
    current=getter(pawn)
    return fields(shield,key),current is not None and identity(current)==token


def validate_readback(shield,key,value):
    name='GetRegenRate' if key=='shield_regen_rate' else 'GetRegenDelay'
    observed=member(shield,name,'ZFloatProperty')()
    if type(observed) not in (int,float) or observed!=value:raise ValueError('native shield getter disagrees with field')
