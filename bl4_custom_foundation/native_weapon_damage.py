"""Opt-in native removable weapon Damage modifier; never invokes an attack."""
from .native_resource_rates import NativeRateTrial, WEAPON_MODE, WEAPON_FIRE, RELOAD_MODE, WEAPON_RELOAD, EligibilityLost, close
from .gameplay_fields import identity
from .weapon_rates import capture, resolve, mode, is_fire, nested


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


def local_resolver(binding,context,weak,trial_mode=WEAPON_MODE):
    scope=None
    reload=trial_mode==RELOAD_MODE
    required=WEAPON_RELOAD if reload else WEAPON_FIRE
    def matches(b):
        return (any(c._path_name()==required for c in (b.Class,*b.Class._superfields())) if reload else is_fire(b))
    def find(cleanup=False):
        nonlocal scope
        pc,pawn,state,ok=context()
        if ok is False and not cleanup:raise EligibilityLost('local weapon session ended')
        if (ok is not True and not (cleanup and ok is False)) or pawn.Class._path_name()!='/Script/OakGame.OakCharacter' or pc.Class._path_name()!='/Script/OakGame.OakPlayerController' or 'Default__' in pawn._path_name() or 'Default__' in pc._path_name() or identity(pc.Pawn)!=identity(pawn):
            raise ValueError('exact local weapon owner required')
        d,dk=binding.definition(trial_mode)
        if scope is None:
            if cleanup:raise ValueError('no original weapon scope')
            scope=capture(pawn,'reload' if reload else 'damage',weak)
        w,b=scope['weapon'](),scope['behavior']()
        fields,eligible=resolve(pawn,scope)
        if (w.Class._path_name()!='/Script/OakGame.OakWeapon' or not any(c._path_name()==required and identity(c)==dk[-1][0] for c in (b.Class,*b.Class._superfields()))):
            raise ValueError('exact native fire behavior required')
        # A single fire behavior across all modes prevents a broad/default mask
        # from affecting a second fire behavior. Reject unknown mode selections.
        if not cleanup and (sum(matches(x) for x in w.behaviors if x is not None)!=1 or dk[-1][1] not in (0,1<<scope['mode'])):
            raise ValueError('ambiguous native weapon fire selector')
        if not cleanup and not eligible:raise EligibilityLost('original equipped weapon changed')
        if not cleanup and getattr(find,'armed',False) is False and str(w.CurrentState)!='Active':raise ValueError('activate with idle weapon')
        fresh=context()
        if fresh[3] is False and not cleanup:raise EligibilityLost('local weapon session ended')
        if (fresh[3] is not True and not (cleanup and fresh[3] is False)) or tuple(identity(x) for x in fresh[:3])!=tuple(identity(x) for x in (pc,pawn,state)):
            raise ValueError('local weapon session changed')
        fields,eligible=resolve(pawn,scope)
        if not cleanup and not eligible:raise EligibilityLost('original equipped weapon changed')
        if not cleanup and sum(matches(x) for x in w.behaviors if x is not None)!=1:
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


class WeaponReloadTrial(WeaponDamageTrial):
    """Native reload attribute only; no reload RPC and no minimum-field writes."""
    def floor(self,objs,key,verify=False):
        from .gameplay_fields import pair
        _,mk=self.binding.definition(RELOAD_MODE,minimum=True)
        if mk[-1]!=key[0][-1]:raise ValueError('minimum selector differs from reload selector')
        fields=pair(nested(objs[4],'MinReloadTime','GbxAttributeFloat'),allow_zero=True)
        vals=tuple(f[3] for f in fields)
        if not all(0<=v<=1e4 for v in vals):raise ValueError('invalid minimum')
        _,eligible=resolve(objs[1],self.resolve.weapon_scope)
        if eligible:
            native=self.binding.calls['GetValueOfAttribute']('weapon_min_reload_time',objs[3],-123456.)
            if type(native) not in (float,int) or not close(native,vals[0]):raise ValueError('minimum native readback mismatch')
        elif not verify:raise EligibilityLost('original reload mode ended')
        return (mk,tuple((identity(f[0]),identity(f[0]._type),f[3]) for f in fields)),max(vals)

    def snapshot(self,restore_verify=False):
        objs,key,d,value=super().snapshot(restore_verify)
        witness,floor=self.floor(objs,key,restore_verify)
        if self.record is None:
            if not close(value,key[1][1]):raise ValueError('reload baseline must equal base')
            self.minimum_witness=witness;self.minimum=floor
        elif witness!=self.minimum_witness:raise ValueError('original minimum changed')
        if value<floor:raise ValueError('reload value below native minimum')
        return objs,key,d,value

    def target_value(self,base):
        target=super().target_value(base)
        if target<self.minimum:raise ValueError('reload target below native minimum')
        return target

    def dispatch_target(self,cleanup=False,restore_verify=False):
        objs,key,d=super().dispatch_target(cleanup,restore_verify)
        if self.phase=='armed' and not cleanup and not restore_verify:
            witness,floor=self.floor(objs,key)
            if witness!=self.minimum_witness or self.target_value(self.baseline)<floor:
                raise ValueError('reload minimum changed before add')
        return objs,key,d

    def stable_snapshot(self,restore_verify=False):
        # Capture both independent minimum observations during admission.
        a=self.snapshot(restore_verify);first=self.minimum_witness
        b=self.snapshot(restore_verify)
        if first!=self.minimum_witness or tuple(identity(x) for x in a[0])!=tuple(identity(x) for x in b[0]) or a[1]!=b[1] or not close(a[3],b[3]):
            raise ValueError('reload witness changed during preflight')
        return b


def make_reload_trial(binding,context,weak,clock,thread,report,permission,selection):
    resolver=local_resolver(binding,context,weak,RELOAD_MODE)
    def allowed():
        if permission() is not True:return False
        if trial.phase=='armed':
            try:trial.dispatch_target()
            except Exception:return False
            return permission() is True
        return True
    trial=WeaponReloadTrial(RELOAD_MODE,binding,resolver,weak,clock,thread,report,allowed,
                            lambda k:(k[0],k[1][0]),selection=selection)
    return trial
