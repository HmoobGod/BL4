"""Opt-in native removable weapon Damage modifier; never invokes an attack."""
from .native_resource_rates import NativeRateTrial, WEAPON_MODE, WEAPON_FIRE, EligibilityLost, close
from .gameplay_fields import identity
from .weapon_rates import capture, resolve, mode, is_fire


class WeaponDamageTrial(NativeRateTrial):
    def begin(self):
        result=super().begin()
        self.resolve.armed=result
        return result

    def read_context(self,objs):
        return objs[3]

    def dispatch_target(self,cleanup=False,restore_verify=False):
        objs,key,d=super().dispatch_target(cleanup,restore_verify)
        if self.phase=='armed' and not cleanup and not restore_verify:
            fields,eligible=resolve(objs[1],self.resolve.weapon_scope)
            if (not eligible or not close(fields[0][3],self.baseline) or str(objs[3].CurrentState)!='Active'):
                raise ValueError('armed original weapon baseline or idle state changed')
        return objs,key,d

    def snapshot(self,restore_verify=False):
        objs,key,d=self.dispatch_target(restore_verify=restore_verify)
        # Cross-check the independent original field, not merely a native getter.
        fields,eligible=resolve(objs[1],self.resolve.weapon_scope)
        value,base=(f[3] for f in fields)
        if not close(base,key[1][1]):raise ValueError('weapon base changed during readback')
        if eligible and mode(objs[3])==self.resolve.weapon_scope['mode']:
            native=self.binding.read(self.mode,objs[3])
            if not close(native,value):raise ValueError('native weapon damage disagrees with original fire field')
        elif not restore_verify:
            raise EligibilityLost('original weapon mode ended')
        # On mode change the retained original field is the removal witness;
        # the active-mode native getter no longer identifies that field.
        again,_=resolve(objs[1],self.resolve.weapon_scope)
        if (identity(again[0][0])!=key[1][0][1] or not close(again[0][3],value) or not close(again[1][3],base)):
            raise ValueError('original weapon damage changed during readback')
        return objs,key,d,value


def local_resolver(binding,context,weak):
    scope=None
    def find(cleanup=False):
        nonlocal scope
        pc,pawn,state,ok=context()
        if ok is False and not cleanup:raise EligibilityLost('local weapon session ended')
        if (ok is not True and not (cleanup and ok is False)) or pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or pc.Class._path_name()!='/Script/OakGame.OakPlayerController' or 'Default__' in pawn._path_name() or 'Default__' in pc._path_name() or identity(pc.Pawn)!=identity(pawn):
            raise ValueError('exact local weapon owner required')
        d,dk=binding.definition(WEAPON_MODE)
        if scope is None:
            if cleanup:raise ValueError('no original weapon scope')
            scope=capture(pawn,'damage',weak)
        w,b=scope['weapon'](),scope['behavior']()
        fields,eligible=resolve(pawn,scope)
        if (w.Class._path_name()!='/Script/OakGame.OakWeapon' or not any(c._path_name()==WEAPON_FIRE and identity(c)==dk[-1][0] for c in (b.Class,*b.Class._superfields()))):
            raise ValueError('exact native fire behavior required')
        # A single fire behavior across all modes prevents a broad/default mask
        # from affecting a second fire behavior. Reject unknown mode selections.
        if not cleanup and (sum(is_fire(x) for x in w.behaviors if x is not None)!=1 or dk[-1][1] not in (0,1<<scope['mode'])):
            raise ValueError('ambiguous native weapon fire selector')
        if not cleanup and not eligible:raise EligibilityLost('original equipped weapon changed')
        if not cleanup and getattr(find,'armed',False) is False and str(w.CurrentState)!='Active':raise ValueError('activate with idle weapon')
        fresh=context()
        if fresh[3] is False and not cleanup:raise EligibilityLost('local weapon session ended')
        if (fresh[3] is not True and not (cleanup and fresh[3] is False)) or tuple(identity(x) for x in fresh[:3])!=tuple(identity(x) for x in (pc,pawn,state)):
            raise ValueError('local weapon session changed')
        fields,eligible=resolve(pawn,scope)
        if not cleanup and not eligible:raise EligibilityLost('original equipped weapon changed')
        if not cleanup and sum(is_fire(x) for x in w.behaviors if x is not None)!=1:
            raise ValueError('late ambiguous native weapon fire selector')
        find.weapon_scope=scope
        key=(dk,((scope['mode'],identity(fields[0][0]),identity(fields[0][0]._type)),fields[1][3]))
        return (pc,pawn,state,w,b),key,d
    find.original=lambda:find(True)
    find.restored=lambda:find(True)
    return find


def make_trial(binding,context,weak,clock,thread,report,permission,selection):
    resolve=local_resolver(binding,context,weak)
    # Allow shooting after the add, but never dispatch while firing. The
    # permission callback is sampled again immediately before the add.
    def allowed():
        if permission() is not True:return False
        if trial.phase=='armed':
            try:trial.dispatch_target()
            except Exception:return False
            return permission() is True
        return True
    trial=WeaponDamageTrial(WEAPON_MODE,binding,resolve,weak,clock,thread,report,allowed,
                            lambda k:(k[0],k[1][0]),selection=selection)
    return trial


def choose_gun_trial(primary,alternative,report):
    """Alternative is legal only after a read-only binding/preflight refusal."""
    try:lane=primary()
    except (AttributeError,TypeError,ValueError) as exc:
        report('HOLD: actor gun binding '+str(exc)[:100])
    else:
        if lane.begin() or lane.record is not None or lane.fault or lane.phase!='idle' or lane.owned:
            return lane
    lane=alternative()
    lane.begin()
    return lane
