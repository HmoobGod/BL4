"""Synthetic melee expression and original-entry lifecycle checks."""
from test_blackboard_rewards import RewardTests
from test_combat_r13 import Node
from test_double_jump_r52 import p,t
from test_native_resource_rates import FGbxDefPtr, WrappedStruct


class MeleeDamageTests(RewardTests):
    def setUp(self):
        super().setUp();R=self.R
        self.keyname=R.MELEE_KEY;self.peer=R.MELEE_PEER
        self.values.update({self.keyname:('Float',1.),self.peer:('Float',1.5),R.GUN_KEY:('Float',1.)})
        actor=t('ActorContextResolver',R.ENGINE+'ActorContextResolver')
        self.defs.definitions[self.keyname]=Node(Context=Node(_type=actor),Value=Node(_type=self.val,Variable=self.key(self.keyname)))
        et=t('GbxAttributeExpression',R.ENGINE+'GbxAttributeExpression')
        resolver=t('GbxExpressionValueResolver',R.ENGINE+'GbxExpressionValueResolver',p('Expression',R.S,Struct=et))
        self.formula_def=Node(Context=Node(_type=actor),Value=Node(_type=resolver,Expression=Node(_type=et)))
        self.defs.definitions[R.MELEE_FORMULA]=self.formula_def
        self.melee=R.MeleeBinding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
        self.override=None;old=self.melee.calls['GetValueOfAttribute']
        def read(k,owner,default):
            if k==R.MELEE_FORMULA:return self.override if self.override is not None else self.values[self.peer][1]+self.values.get(self.keyname,('Float',1.))[1]-1.
            return old(k,owner,default)
        self.melee.calls['GetValueOfAttribute']=read
    def trial(self,scale=2.):
        return self.R.MeleeTrial(self.R.MELEE_MODE,scale,self.melee,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def test_melee_cycle(self):
        l=self.trial();self.assertTrue(l.begin(),self.messages);self.tick(l);self.assertEqual(l.phase,'active',self.messages);self.assertEqual(self.values[self.keyname][1],2.)
        l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(self.values[self.keyname][1],1.);self.assertEqual([c[0] for c in self.calls],[self.keyname]*2)
    def test_melee_absent(self):
        del self.values[self.keyname];self.assertFalse(self.trial().begin());self.assertFalse(self.calls)
    def test_melee_formula_wrong(self):
        self.override=8.;self.assertFalse(self.trial().begin());self.assertFalse(self.calls)
    def test_melee_formula_missing(self):
        del self.defs.definitions[self.R.MELEE_FORMULA];self.assertFalse(self.trial().begin());self.assertFalse(self.calls)
    def test_melee_wrong_resolver(self):
        self.formula_def.Value._type=t('Wrong','/Script/GbxEngine.Wrong');self.assertFalse(self.trial().begin());self.assertFalse(self.calls)
    def test_melee_wrong_type(self):
        self.values[self.keyname]=('Int',1);self.assertFalse(self.trial().begin());self.assertFalse(self.calls)
    def test_melee_nonresponsive(self):
        l=self.trial();self.assertTrue(l.begin());self.override=1.5;self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.keyname][1],1.);self.assertEqual(len(self.calls),2)
    def test_melee_peer_changed(self):
        l=self.trial();self.assertTrue(l.begin());self.values[self.peer]=('Float',2.);self.tick(l);self.assertFalse(self.calls)
    def test_melee_peer_drift_cleanup(self):
        l=self.trial();self.assertTrue(l.begin());self.tick(l);self.values[self.peer]=('Float',2.);self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.keyname][1],1.);self.assertEqual(self.values[self.peer][1],2.)
    def test_melee_join_cleanup(self):
        l=self.trial();self.assertTrue(l.begin());self.tick(l);self.ok=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(len(self.calls),2)
    def test_melee_replaced_board(self):
        l=self.trial();self.assertTrue(l.begin());self.pawn.blackboard=Node(_type=self.pawn.blackboard._type);self.tick(l);self.assertFalse(self.calls)
    def test_melee_permission(self):
        l=self.trial();self.assertTrue(l.begin());self.permission=False;self.tick(l);self.assertFalse(self.calls)
    def test_melee_formula_lost_cleanup(self):
        l=self.trial();self.assertTrue(l.begin());self.tick(l);del self.defs.definitions[self.R.MELEE_FORMULA];self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.keyname][1],1.)
    def test_melee_selection(self):
        for x in (0.,1.,6.,True):
            with self.assertRaises(ValueError):self.trial(x)
    def test_melee_dispatch(self):
        m=self.base.m;seen=[];m.begin_blackboard_reward=lambda k,v:seen.append((k,v));m.execute_activation(m.MELEE_TRIAL_KEY,2.);self.assertEqual(seen,[(m.MELEE_TRIAL_KEY,2.)])
