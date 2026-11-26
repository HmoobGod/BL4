"""Experimental equipped grenade-gadget cooldown only; no charges or attack calls."""
from .gameplay_fields import identity, pair
from .weapon_rates import prop, nested
KEY='grenade_cooldown'
GADGET='/Script/OakGame.GrenadeGadget'
GETTER='/Script/OakGame.OakCharacter:GetGrenadeGadget'

def equipped(pawn):
    bound=pawn.GetGrenadeGadget; fn=bound.func
    ps=tuple(fn._properties())
    if (fn._path_name()!=GETTER or fn.NumParams!=1 or len(ps)!=1
        or str(ps[0].Name)!='ReturnValue' or type(ps[0]).__name__!='ZObjectProperty'
        or ps[0].ArrayDim!=1 or ps[0].PropertyClass._path_name()!=GADGET):
        raise ValueError('grenade gadget getter signature mismatch')
    return bound()

def owned(g,pawn):
    if (g is None or g.Class._path_name()!=GADGET or 'Default__' in g._path_name()
        or g.HasAuthority() is not True or g.IsActorBeingDestroyed() is not False):
        raise ValueError('live authoritative grenade gadget required')
    d=prop(g.Class,'OwningCharacter','ZObjectProperty')
    if d.PropertyClass._path_name()!='/Script/OakGame.OakCharacter' or identity(g.OwningCharacter)!=identity(pawn):
        raise ValueError('grenade gadget owner mismatch')
    if g.Owner is not None and identity(g.Owner)!=identity(pawn):raise ValueError('grenade actor owner mismatch')
    prop(g.Class,'bIsUsing','ZBoolProperty')
    if type(g.bIsUsing) is not bool:raise ValueError('grenade use state unknown')

def fields(g):return pair(nested(g,'CooldownTime','GbxAttributeFloat'))

def capture(pawn,weak):
    g=equipped(pawn);owned(g,pawn)
    if g.bIsUsing:raise ValueError('wait until grenade gadget is idle')
    fields(g)
    return weak(g),identity(g)

def resolve(pawn,scope):
    ref,token=scope;g=ref()
    if g is None or identity(g)!=token:raise ValueError('original grenade gadget lost')
    owned(g,pawn);current=equipped(pawn)
    owned(g,pawn)  # getter may synchronously change ownership
    return fields(g),current is not None and identity(current)==token
