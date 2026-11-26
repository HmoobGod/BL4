"""Bounded opt-in normal reload request; no ammo writes, grants or input injection."""
from .gameplay_fields import identity
from .health_pulse import enum_name
from .weapon_rates import active_weapon, mode, matching_behavior, nested, prop, live

PATH = '/Script/GbxWeapon.WeaponStatics:'
REQUEST = '/Script/GbxWeapon.Weapon:ServerStartReloading'
SPECS = {
    'GetLoadedAmmo': (('Weapon','ZObjectProperty'),('UseMode','ZByteProperty'),('ReturnValue','ZIntProperty')),
    'GetMaxLoadedAmmo': (('Weapon','ZObjectProperty'),('UseMode','ZByteProperty'),('ReturnValue','ZIntProperty')),
    'IsLocalWeaponAuthority': (('WeaponUser','ZObjectProperty'),('ReturnValue','ZBoolProperty')),
}
REQUEST_SIG = (('UseModeIndex','ZByteProperty'),('Flags_0','ZByteProperty'))


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


class ReloadAssist:
    def __init__(self,context,weak,api,fn,clock,thread,report,continuous=False):
        self.context,self.weak,self.api,self.fn=context,weak,api,fn
        self.continuous=continuous
        self.clock,self.thread,self.report=clock,thread,report
        self.record=None;self.fault=False;self.busy=False
        self.previous=None;self.empty_seen=False;self.waiting=False;self.saw_reload=False;self.completed=0;self.completion_samples=0;self.completion_deadline=0

    def resolve(self):
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
            if self.thread()!=tid or key!=original or any(r() is None or identity(r())!=i for r,i in zip(refs,key[0],strict=True)):
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

    def begin(self):
        if self.record is not None or self.fault or self.busy:return False
        try:
            objs,key,_,loaded,_,reserve,state=self.resolve()
            if state!='Active' or not loaded or min(reserve)<=0:raise ValueError('arm with idle loaded gun and reserve ammo')
            now=self.clock();self.record=(tuple(self.weak(o) for o in objs),key,self.thread(),now+30,now+.1)
            self.previous=loaded;self.empty_seen=False
            self.waiting=False;self.saw_reload=False;self.completed=0;self.completion_samples=0;self.completion_deadline=0
        except Exception as e:self.report('HOLD: auto reload '+str(e)[:120]);return False
        self.report('EXPERIMENT: continuous reload armed for 30 sec' if self.continuous else 'EXPERIMENT: auto reload armed; one normal reload request within 30 sec');return True

    def stop(self,reason):
        if self.record is not None:
            self.record=None;self.previous=None;self.empty_seen=False
            self.report('STOP: auto reload '+reason+'; an already started normal reload is not cancelled')

    def tick(self,permitted):
        if self.record is None or self.busy:return
        refs,key,tid,end,due=self.record;now=self.clock()
        if not permitted or self.thread()!=tid or now>=end:self.stop('permission/thread/lifetime ended');return
        if now<due:return
        snapshot=self.record;self.busy=True
        try:
            try:_,_,_,loaded,maximum,reserve,state=self.resolve()
            except Exception as e:self.stop(str(e)[:120]);return
            if self.record is not snapshot:return
            self.record=(refs,key,tid,end,now+.1)
            if min(reserve)<=0:self.stop('no confirmed reserve');return
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
                    self.waiting=False;self.previous=loaded;self.empty_seen=False
                    self.report('EXPERIMENT: reload state and positive idle magazine observed; new cycle armed')
                return
            if state not in ('Active','Using','Firing'):
                self.stop('native reload or other state transition');return
            if loaded>0:
                self.previous=loaded;self.empty_seen=False;return
            if self.previous and loaded==0:
                self.empty_seen=True;self.previous=0;return
            if not self.empty_seen or state!='Active':return
            try:
                fresh=self.resolve()
                last=self.context()
                if self.record is None:return
                if not last[3] or tuple(identity(o) for o in last[:3])!=key[0][:3] or self.clock()>=end or fresh[3]!=0 or fresh[4]!=maximum or min(fresh[5])<=0 or fresh[6]!='Active':
                    self.stop('reload preflight changed');return
            except Exception as e:self.stop(str(e)[:120]);return
            # Keep the lease active and busy during dispatch; reentrant ticks cannot repeat it.
            self.empty_seen=False;self.previous=0
            try:
                if self.continuous:
                    self.waiting=True;self.saw_reload=False;self.completion_samples=0
                    self.completion_deadline=min(end,self.clock()+10.)
                fresh[2](key[1],0)
                if self.record is None:return
                self.completed+=1
                if not self.continuous:
                    self.stop('one native request completed')
                    self.report('EXPERIMENT: normal reload requested once; actual outcome unverified')
                elif self.completed>=10:
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
