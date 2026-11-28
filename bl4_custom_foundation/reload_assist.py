"""Bounded opt-in normal reload request; no ammo writes, grants or input injection."""
from collections import deque
from .gameplay_fields import identity
from .health_pulse import enum_name
from .weapon_rates import active_weapon, mode, matching_behavior, nested, prop, live, slot_entries, weapons_from_entries, STATES

PATH = '/Script/GbxWeapon.WeaponStatics:'
REQUEST = '/Script/GbxWeapon.Weapon:ServerStartReloading'
RELOAD_ENDED_PATH = '/Script/OakGame.OakUIDataCollector_WeaponStatus:OnReloadEnded'
TRANSITION_STATES = frozenset(('Inactive', 'Equipping', 'PuttingDown'))
SPECS = {
    'GetLoadedAmmo': (('Weapon','ZObjectProperty'),('UseMode','ZByteProperty'),('ReturnValue','ZIntProperty')),
    'GetMaxLoadedAmmo': (('Weapon','ZObjectProperty'),('UseMode','ZByteProperty'),('ReturnValue','ZIntProperty')),
    'IsLocalWeaponAuthority': (('WeaponUser','ZObjectProperty'),('ReturnValue','ZBoolProperty')),
}
REQUEST_SIG = (('UseModeIndex','ZByteProperty'),('Flags_0','ZByteProperty'))


def behavior_use_mode_index(behavior):
    """Parse native BL4 multi-mode behavior names such as UM0_... / UM1_... to an int index."""
    try:
        name = str(behavior.Name)
    except Exception:
        return None
    if not name.startswith('UM'):
        return None
    digits = []
    for ch in name[2:]:
        if not ch.isdigit():
            break
        digits.append(ch)
    return int(''.join(digits)) if digits else None


def bind(functions, existing):
    out = []
    for name, sig in SPECS.items():
        matches = [f for f in functions if f._path_name() == PATH+name]
        if len(matches) != 1:
            raise ValueError('reload getter missing or ambiguous')
        fn = matches[0]; ps = tuple(fn._properties())
        target = '/Script/Engine.Actor' if name == 'IsLocalWeaponAuthority' else '/Script/GbxWeapon.Weapon'
        if not ps or any(p.ArrayDim != 1 for p in ps) or ps[0].PropertyClass._path_name() != target or fn.Outer._path_name() != PATH[:-1]:
            raise ValueError('reload getter descriptor mismatch')
        out.append(existing(functions, PATH+name, sig))
    matches = [f for f in functions if f._path_name() == REQUEST]
    if len(matches) != 1:
        raise ValueError('reload request missing or ambiguous')
    f = matches[0]; ps = tuple(f._properties())
    if f.Outer._path_name() != REQUEST.rsplit(':',1)[0] or f.NumParams != 2 or tuple((str(p.Name),type(p).__name__) for p in ps) != REQUEST_SIG or any(p.ArrayDim != 1 for p in ps):
        raise ValueError('reload request signature mismatch')
    return tuple(out), f


def count(v):
    if type(v) is not int or not 0 <= v <= 10**7:
        raise ValueError('invalid magazine or reserve count')
    return v


class ReloadCompletionObserver:
    """Read-only native OnReloadEnded event witness for an active ReloadAssist."""

    def __init__(self, assist, thread):
        self.assist = assist
        self.thread = thread
        self.events = 0

    def on_reload_ended(self, obj, args):
        try:
            weapon = getattr(args, 'EventWeapon', None)
            if weapon is None:
                return
            if self.assist.note_reload_ended(weapon, self.thread()):
                self.events += 1
        except Exception:
            return


class ReloadAssist:
    def __init__(self,context,weak,api,fn,clock,thread,report,continuous=False,session_mode=False,recover_mid_reload_swap=False):
        self.context,self.weak,self.api,self.fn=context,weak,api,fn
        self.continuous=continuous
        self.session_mode=session_mode and continuous
        self.recover_mid_reload_swap=bool(recover_mid_reload_swap) and self.session_mode
        self.clock,self.thread,self.report=clock,thread,report
        self.record=None;self.fault=False;self.busy=False
        self.recent=deque();self.swap_paused=False;self.reserve_paused=False
        self.previous=None;self.empty_seen=False;self.waiting=False;self.saw_reload=False;self.completed=0;self.completion_samples=0;self.completion_deadline=0

    def note_reload_ended(self, weapon, tid=None):
        """Record a witnessed native OnReloadEnded event for the pinned active weapon."""
        if self.record is None or not self.waiting:
            return False
        refs, key, expected_tid, _, _ = self.record
        if tid is not None and tid != expected_tid:
            return False
        if len(key[0]) <= 3 or refs[3]() is None:
            return False
        if identity(weapon) != key[0][3] or identity(refs[3]()) != key[0][3]:
            return False
        self.saw_reload = True
        return True

    def resolve(self, check_weapon=True):
        pc,pawn,state,ok=self.context()
        if not ok or enum_name(pawn.HealthCondition)!='Healthy' or self.api[2](pawn) is not True:
            raise ValueError('eligible healthy local weapon authority required')
        w=active_weapon(pawn);index=mode(w)
        reload=matching_behavior(w,'reload',index)
        pool=matching_behavior(w,'ammo_regen_rate',index)
        fire=matching_behavior(w,'fire_rate',index)
        objs=(pc,pawn,state,w,reload,pool,fire)
        key=(tuple(identity(o) for o in objs),index)
        if self.record is not None:
            refs,original,tid,end,due=self.record
            if self.thread()!=tid or key[0][:3]!=original[0][:3] or any(r() is None or identity(r())!=i for r,i in zip(refs[:3],key[0][:3],strict=True)) or (check_weapon and (key!=original or any(r() is None or identity(r())!=i for r,i in zip(refs[3:],key[0][3:],strict=True)))):
                raise ValueError('original weapon/mode/behavior/session changed')
        for n in ('LoadedAmmo','StoredAmmo','SpareAmmo','ServerSyncedLoadedAmmo'):
            prop(pool.Class,n,'ZIntProperty')
        maxattr=nested(pool,'MaxLoadedAmmo','GbxAttributeInteger')
        prop(maxattr._type,'Value','ZIntProperty')
        loaded,maximum=(count(f(w,index)) for f in self.api[:2])
        reserve=(count(pool.StoredAmmo),count(pool.SpareAmmo))
        if loaded!=count(pool.LoadedAmmo) or loaded!=count(pool.ServerSyncedLoadedAmmo) or maximum!=count(maxattr.Value) or not 0<=loaded<=maximum or maximum==0:
            raise ValueError('magazine readback disagreement')
        bound=w.ServerStartReloading
        if identity(bound.func)!=identity(self.fn) or bound.func._path_name()!=REQUEST:
            raise ValueError('bound reload function mismatch')
        return objs,key,bound,loaded,maximum,reserve,str(w.CurrentState)

    def session_owner(self):
        pc,pawn,state,ok=self.context()
        if not ok or enum_name(pawn.HealthCondition)!='Healthy' or self.api[2](pawn) is not True:
            raise ValueError('eligible healthy local weapon authority required')
        return pc,pawn,state

    def waiting_for_weapon(self,pawn):
        # Only positively observed empty/transitioning slots are a benign wait.
        # Ambiguous, foreign, unsupported and malformed active weapons still fail closed.
        entries=slot_entries(pawn)
        if any(s.PendingWeapon is not None or s.ClientPredictedPendingWeapon is not None for s in entries):
            return True
        states=tuple(str(w.CurrentState) for w in weapons_from_entries(entries).values())
        if any(state in STATES for state in states):return False
        if any(state not in TRANSITION_STATES for state in states):raise ValueError('unknown weapon state during wait')
        return True

    def begin(self):
        if self.record is not None or self.fault or self.busy:return False
        try:
            waiting=False
            if self.session_mode:
                owner=self.session_owner()
                if self.waiting_for_weapon(owner[1]):
                    objs=owner;key=(tuple(identity(o) for o in owner),None)
                    loaded=None;waiting=True
                else:
                    objs,key,_,loaded,_,reserve,state=self.resolve()
                    if key[0][:3]!=tuple(identity(o) for o in owner):raise ValueError('session changed during arm')
                    waiting=state!='Active' or not loaded or min(reserve)<=0
                if tuple(identity(o) for o in self.session_owner())!=key[0][:3]:raise ValueError('session changed during arm')
            else:
                objs,key,_,loaded,_,reserve,state=self.resolve()
                if state!='Active' or not loaded or min(reserve)<=0:raise ValueError('arm with idle loaded gun and reserve ammo')
            now=self.clock();self.record=(tuple(self.weak(o) for o in objs),key,self.thread(),float("inf") if self.session_mode else now+30,now+.1)
            self.previous=None if waiting else loaded;self.empty_seen=False
            self.waiting=False;self.saw_reload=False;self.completed=0;self.completion_samples=0;self.completion_deadline=0
            self.recent.clear();self.swap_paused=waiting;self.reserve_paused=False
        except Exception as e:self.report('HOLD: auto reload '+str(e)[:120]);return False
        self.report('EXPERIMENT: session reload armed (ten requests per rolling 30s; supported idle swaps)' if self.session_mode else 'EXPERIMENT: continuous reload armed for 30 sec' if self.continuous else 'EXPERIMENT: auto reload armed; one normal reload request within 30 sec');return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.previous=None;self.empty_seen=False
            self.report('STOP: auto reload '+reason+'; an already started normal reload is not cancelled')

    def _clear_waiting_on_swap(self):
        self.waiting=False;self.saw_reload=False;self.completion_samples=0;self.completion_deadline=0

    def session_sample(self, snapshot):
        """Only retarget between requests, in the same weakly pinned player/session.
        A pending transition suppresses all requests; a replacement must be idle
        and loaded. Never transfer an empty-magazine or completion witness.
        """
        refs,key,tid,end,due=snapshot
        pc,pawn,state,ok=self.context()
        if (not ok or self.thread()!=tid or enum_name(pawn.HealthCondition)!='Healthy'
                or tuple(identity(o) for o in (pc,pawn,state))!=key[0][:3]
                or any(r() is None or identity(r())!=i for r,i in zip(refs[:3],key[0][:3],strict=True))
                or self.api[2](pawn) is not True):
            raise ValueError('original reload session changed')
        if self.waiting_for_weapon(pawn):
            if self.waiting:
                if not self.recover_mid_reload_swap:raise ValueError('swap during unconfirmed reload')
                self._clear_waiting_on_swap()
            if self.record is snapshot:
                self.swap_paused=True;self.previous=None;self.empty_seen=False
                self.record=(refs,key,tid,end,self.clock()+.1)
            return None
        sample=self.resolve(check_weapon=False)
        if self.record is not snapshot:return None
        objs,fresh_key,_,loaded,_,reserve,native_state=sample
        changed=fresh_key!=key
        if changed and len(key[0])>3 and fresh_key[0][3]==key[0][3]:
            # A new mode must resolve to distinct native behaviors on the same live weapon.
            # Never adopt a same-mode replacement or a recycled weapon address.
            if (fresh_key[1]==key[1] or refs[3]() is None or identity(refs[3]())!=fresh_key[0][3]
                    or set(fresh_key[0][4:]) & set(key[0][4:])):
                raise ValueError('same weapon mode or behavior changed without distinct scope')
        # Even during a benign wait, a recycled same-scope address is not a new weapon.
        if not changed and any(r() is None or identity(r())!=i for r,i in zip(refs[3:],key[0][3:],strict=True)):
            raise ValueError('original weapon identity lost')
        if changed or self.swap_paused:
            if self.waiting:
                if not self.recover_mid_reload_swap:raise ValueError('swap during unconfirmed reload')
                self._clear_waiting_on_swap()
            if native_state not in STATES:raise ValueError('unsupported replacement state')
            new_refs=tuple(self.weak(o) for o in objs)
            if self.record is not snapshot:return None
            if tuple(identity(o) for o in self.session_owner())!=fresh_key[0][:3]:raise ValueError('session changed during weapon admission')
            if self.record is not snapshot:return None
            ready=native_state=='Active' and loaded>0 and min(reserve)>0
            self.record=(new_refs,fresh_key,tid,end,self.clock()+.1)
            self.previous=None;self.empty_seen=False;self.swap_paused=not ready;self.reserve_paused=False
            if ready:self.report('EXPERIMENT: supported idle weapon admitted; awaiting fresh positive magazine sample')
            elif changed:self.report('PAUSE: supported replacement not ready; waiting for loaded idle magazine and reserve')
            return None
        return sample

    def tick(self,permitted):
        if self.record is None or self.busy:return
        refs,key,tid,end,due=self.record;now=self.clock()
        if not permitted or self.thread()!=tid or now>=end:self.stop('permission/thread/lifetime ended');return
        if now<due:return
        snapshot=self.record;self.busy=True
        try:
            try:
                sample=self.session_sample(snapshot) if self.session_mode else self.resolve()
                if sample is None:return
                _,_,_,loaded,maximum,reserve,state=sample
            except Exception as e:self.stop(str(e)[:120]);return
            if self.record is not snapshot:return
            self.record=(refs,key,tid,end,now+.1)
            # The last reserve rounds may legitimately be consumed by an in-flight
            # reload. Observe completion without issuing another request.
            if min(reserve)<=0 and not (self.session_mode and (self.waiting or state=='Reloading')):
                if not self.session_mode or self.waiting or state not in ('Active','Using','Firing'):
                    self.stop('no confirmed reserve');return
                if not self.reserve_paused:self.report('PAUSE: no confirmed reserve; waiting for ammo and a fresh loaded idle sample')
                self.reserve_paused=True;self.previous=None;self.empty_seen=False;return
            if self.reserve_paused:
                if state not in ('Active','Using','Firing','Reloading'):
                    self.stop('unsupported state during reserve recovery');return
                if state=='Active' and loaded>0:
                    self.reserve_paused=False;self.previous=loaded;self.empty_seen=False
                    self.report('EXPERIMENT: reserve recovered with positive idle magazine; new cycle armed')
                return
            if self.waiting:
                if now>=self.completion_deadline:
                    self.stop('reload completion not observed');return
                if state=='Reloading':
                    self.saw_reload=True;self.completion_samples=0;return
                if state!='Active' or not loaded or not self.saw_reload:
                    # Do not treat an external ammo increase or interrupted reload as completion.
                    if state not in ('Active','Reloading') or (loaded and not self.saw_reload):
                        self.stop('unconfirmed reload completion');return
                    self.completion_samples=0;return
                self.completion_samples+=1
                if self.completion_samples>=2:
                    self.waiting=False;self.reserve_paused=self.session_mode and min(reserve)<=0
                    self.previous=None if self.reserve_paused else loaded;self.empty_seen=False
                    self.report('PAUSE: reload completed; reserve exhausted' if self.reserve_paused else 'EXPERIMENT: reload state and positive idle magazine observed; new cycle armed')
                return
            if self.session_mode and state=='Reloading':
                # A manual/native reload is already underway. Observe, never dispatch.
                self.waiting=True;self.saw_reload=True;self.completion_samples=0
                self.completion_deadline=min(end,now+10.)
                self.previous=None;self.empty_seen=False
                self.report('EXPERIMENT: external reload observed; waiting for native completion')
                return
            if state not in ('Active','Using','Firing'):
                self.stop('native reload or other state transition');return
            if loaded>0:
                self.previous=loaded;self.empty_seen=False;return
            if self.previous and loaded==0:
                self.empty_seen=True;self.previous=0;return
            if not self.empty_seen or state!='Active':return
            if self.session_mode:
                while self.recent and self.recent[0]<=now-30:self.recent.popleft()
                if len(self.recent)>=10:return
            try:
                fresh=self.resolve()
                last=self.context()
                if self.record is None:return
                if not last[3] or tuple(identity(o) for o in last[:3])!=key[0][:3] or self.clock()>=end or fresh[3]!=0 or fresh[4]!=maximum or min(fresh[5])<=0 or fresh[6]!='Active':
                    self.stop('reload preflight changed');return
                # The final session getter can synchronously change the equipped
                # weapon, mode, pool, ammo or health. Confirm the original live
                # weapon and reflected counts AFTER that getter, not just before.
                # This is only on the native dispatch path, not the idle poll.
                pawn=last[1];w=active_weapon(pawn);index=mode(w)
                reload=matching_behavior(w,'reload',index)
                pool=matching_behavior(w,'ammo_regen_rate',index)
                fire=matching_behavior(w,'fire_rate',index)
                final_objects=(*last[:3],w,reload,pool,fire)
                if ((tuple(identity(o) for o in final_objects),index)!=key
                        or any(r() is None or identity(r())!=i for r,i in zip(refs,key[0],strict=True))
                        or enum_name(pawn.HealthCondition)!='Healthy' or str(w.CurrentState)!='Active'
                        or count(pool.LoadedAmmo)!=0 or count(pool.ServerSyncedLoadedAmmo)!=0
                        or count(nested(pool,'MaxLoadedAmmo','GbxAttributeInteger').Value)!=maximum
                        or min(count(pool.StoredAmmo),count(pool.SpareAmmo))<=0
                        or identity(w.ServerStartReloading.func)!=identity(self.fn)
                        or self.thread()!=tid or self.clock()>=end or self.record is None):
                    self.stop('final original reload scope or magazine changed');return
            except Exception as e:self.stop(str(e)[:120]);return
            # Keep the lease active and busy during dispatch; reentrant ticks cannot repeat it.
            self.empty_seen=False;self.previous=0
            try:
                if self.continuous:
                    self.waiting=True;self.saw_reload=False;self.completion_samples=0
                    self.completion_deadline=min(end,self.clock()+10.)
                if self.session_mode:self.recent.append(self.clock())
                fresh[2](key[1],0)
                if self.record is None:return
                self.completed+=1
                if not self.continuous:
                    self.stop('one native request completed')
                    self.report('EXPERIMENT: normal reload requested once; actual outcome unverified')
                elif not self.session_mode and self.completed>=10:
                    self.stop('maximum ten distinct requests reached')
                else:
                    # A fast reload can start and end between camera samples.
                    # Observe the original scoped weapon immediately after dispatch.
                    # A failed observation is not a second request or a dispatch fault.
                    try:
                        observed=self.resolve()
                        if self.record is None:return
                        if observed[6]=='Reloading':self.saw_reload=True
                        elif observed[6]!='Active' or observed[3]>0:
                            self.stop('unconfirmed immediate reload state');return
                    except Exception as e:
                        self.stop('post-request observation failed: '+str(e)[:100]);return
                    self.report('EXPERIMENT: reload requested; waiting for native completion')
            except Exception:
                self.fault=True;self.stop('native reload dispatch uncertain');self.report('FAULT: native reload request uncertain; exit game')
        finally:self.busy=False
