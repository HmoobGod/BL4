import unittest
from test_foundation import Test
from test_combat_r13 import Node
from test_double_jump_r52 import p,t
from test_native_resource_rates import FGbxDefPtr,WrappedStruct

class RewardTests(unittest.TestCase):
    def setUp(self):
        self.base=Test();self.base.setUp();self.addCleanup(self.base.tearDown)
        from bl4_custom_foundation import blackboard_rewards as R
        self.R=R;self.time=0.;self.tid=1;self.ok=True;self.permission=True;self.calls=[];self.messages=[];self.corrupt=False;self.peer_drift=False
        self.entry=t('GbxBlackboardEntryRef',R.ENTRY,p('Name',R.N));self.param=t('GbxParam',R.PARAM)
        self.defs=t('GbxAttributeDef',R.DEF,p('Context','ZGbxInlineStructProperty'),p('Value','ZGbxInlineStructProperty'));self.defs.definitions={}
        self.ctx=t('GbxBlackboardOwnerContextResolver',R.ENGINE+'GbxBlackboardOwnerContextResolver');self.val=t('GbxBlackboardValueResolver',R.ENGINE+'GbxBlackboardValueResolver',p('Variable',R.S,Struct=self.entry))
        self.values={n:('Float',float(i+1)) for i,n in enumerate(R.TARGETS.values())}
        for n in self.values:self.defs.definitions[n]=Node(Context=Node(_type=self.ctx),Value=Node(_type=self.val,Variable=self.key(n)))
        bb=t('GbxBlackboard',R.ENGINE+'GbxBlackboard');self.pawn=Node(Class=t('OakCharacter','/Script/OakGame.OakCharacter',p('blackboard',R.S,Struct=bb)),blackboard=Node(_type=bb),Name='Pawn');self.pc=Node(Pawn=self.pawn);self.state=Node()
        self.fs=[]
        for n,(lib,sig) in R.SPECS.items():
            ps=[p(k,kind) for k,kind in sig]
            for d in ps:
                if type(d).__name__==R.S:d.Struct=self.entry if d.Name=='BlackboardKey' else self.param
                if type(d).__name__==R.O:d.PropertyClass=Node(Name='/Script/CoreUObject.Object')
            self.fs.append(Node(Name=n,Outer=Node(Name=R.ENGINE+lib),NumParams=len(ps),_properties=lambda ps=ps:ps,_path_name=lambda n=n,lib=lib:R.ENGINE+lib+':'+n))
        self.binding=self.bind()
    def bind(self):return self.R.Binding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
    def key(self,n):return WrappedStruct(_type=self.entry,Name=n)
    def param_obj(self,kind,v):return WrappedStruct(_type=self.param,kind=kind,v=v)
    def bound(self,fs,path,sig):
        n=path.rsplit(':',1)[1]
        if n in ('Conv_GbxParamToString','GetSummary_GbxParam'):return lambda p:(('None' if p.kind=='None' else f'{p.kind}: {p.v}'),p)
        if n.startswith('Conv_'):return lambda v:self.param_obj(n.split('_')[1].split('To')[0],v)
        if n=='GetBlackboardParamPure':return lambda k,pawn,report:(self.param_obj(*self.values.get(k.Name,('None',0.))),k)
        if n=='GetBlackboardFloatPure':return lambda k,pawn,report:(float(self.values.get(k.Name,('None',0.))[1]),k)
        if n=='GetValueOfAttribute':return lambda key,pawn,default:self.values.get(key,('None',default))[1]
        if n=='SetBlackboardParam':return self.write
        raise AssertionError(n)
    def write(self,k,p,pawn):
        assert pawn is self.pawn
        self.calls.append((k.Name,p.kind,p.v));self.values[k.Name]=(p.kind,p.v)
        if self.peer_drift and len(self.calls)==1:self.values[next(n for n in self.values if n!=k.Name)]=('Float',99.)
        if self.corrupt and len(self.calls)==1:return None
        return Ellipsis,k,p
    def lane(self,key='progress_enemy_xp',scale=2.):return self.R.Trial(key,scale,self.binding,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def tick(self,lane,dt=.6,permit=True):self.time+=dt;lane.tick(permit)
    def cycle(self,key):
        old=dict(self.values);l=self.lane(key);self.assertTrue(l.begin());self.assertFalse(self.calls);self.tick(l);self.assertEqual(l.phase,'active');self.assertEqual(self.values[l.name][1],old[l.name][1]*2);self.assertEqual(len(self.calls),1);l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(self.values,old);self.assertEqual(len(self.calls),2)
    def test_xp(self):self.cycle('progress_enemy_xp')
    def test_cash(self):self.cycle('progress_money')
    def test_eridium(self):self.cycle('progress_eridium')
    def test_absent(self):
        l=self.lane();del self.values[l.name];self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_wrong_type(self):
        l=self.lane();self.values[l.name]=('Int',1);self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_missing_collision(self):
        l=self.lane();self.values[self.R.MISSING]=self.values[l.name];self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_second_missing_collision(self):
        l=self.lane();self.values[self.R.MISSING+'_B']=('Float',2.);self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_wrong_resolver(self):
        l=self.lane();self.defs.definitions[l.name].Context._type=Node(Name='wrong');self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_wrong_key(self):
        l=self.lane();self.defs.definitions[l.name].Value.Variable.Name='wrong';self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_permission(self):
        l=self.lane();self.permission=False;self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_permission_withdrawn(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);self.permission=False;self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(len(self.calls),2)
    def test_scope_changed(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);self.state=Node();self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),1)
    def test_wrong_thread(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);self.tid=2;self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),1)
    def test_drift_not_overwritten(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);self.values[l.name]=('Float',3.);self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),1)
    def test_uncertain_setter(self):
        l=self.lane();self.assertTrue(l.begin());self.corrupt=True;self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),2);self.assertEqual(self.values[l.name],('Float',1.))
    def test_peer_drift(self):
        l=self.lane();self.assertTrue(l.begin());self.peer_drift=True;self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),2);self.assertEqual(self.values[l.name],('Float',1.))
    def test_expiry(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);self.tick(l,30.);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(len(self.calls),2)
    def test_stopped_before_dispatch(self):
        l=self.lane();self.assertTrue(l.begin());l.stop('test');self.tick(l);self.assertFalse(self.calls)
    def test_bound(self):
        for scale in (1,True,11,float('nan')):
            with self.assertRaises(ValueError):self.lane(scale=scale)
    def test_bad_signature(self):
        self.fs[0].NumParams=99
        with self.assertRaises(ValueError):self.bind()
    def test_api_missing(self):
        self.fs.pop()
        with self.assertRaises(ValueError):self.bind()
    def test_delayed_drift(self):
        l=self.lane();self.assertTrue(l.begin());self.tick(l);l.stop('test');self.tick(l);self.values[l.name]=('Float',2.);self.tick(l);self.assertTrue(l.fault);self.assertEqual(len(self.calls),2)
    def test_unsupported_key(self):
        with self.assertRaises(ValueError):self.lane('progress_mission_xp')
    def test_no_default_when_zero(self):
        l=self.lane();self.values[l.name]=('Float',0.);self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_queue_dispatch(self):
        m=self.base.m;self.assertEqual(m.REWARD_KEYS,set(self.R.TARGETS))
        seen=[];m.begin_blackboard_reward=lambda k,v:seen.append((k,v));m.execute_activation('progress_money',2.);self.assertEqual(seen,[('progress_money',2.)])
