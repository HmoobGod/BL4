"""Synthetic cash consumer witnesses; never executes the native game."""
from test_blackboard_rewards import RewardTests
from test_combat_r13 import Node
from test_double_jump_r52 import p,t
from test_native_resource_rates import FGbxDefPtr, WrappedStruct


class CashFormulaTests(RewardTests):
    def setUp(self):
        super().setUp();R=self.R
        self.generic=R.CASH_GENERIC;self.primary=R.TARGETS['progress_money']
        self.values[self.generic]=('Float',1.5)
        self.defs.definitions[self.generic]=Node(Context=Node(_type=self.ctx),Value=Node(_type=self.val,Variable=self.key(self.generic)))
        et=t('GbxAttributeExpression',R.ENGINE+'GbxAttributeExpression')
        resolver=t('GbxExpressionValueResolver',R.ENGINE+'GbxExpressionValueResolver',p('Expression',R.S,Struct=et))
        actor=t('ActorContextResolver',R.ENGINE+'ActorContextResolver')
        self.formula_def=Node(Context=Node(_type=actor),Value=Node(_type=resolver,Expression=Node(_type=et)))
        self.defs.definitions[R.CASH_FORMULA]=self.formula_def
        self.level=25.;self.override=None
        self.binding=R.CashFormulaBinding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
        original=self.binding.calls['GetValueOfAttribute']
        def read(k,owner,default):
            if k==R.CASH_LEVEL:return self.level
            if k==R.CASH_FORMULA:return self.override if self.override is not None else 4*self.level*self.values.get(self.primary,('Float',1.))[1]*self.values[self.generic][1]
            if k==self.primary:return self.values.get(k,('Float',1.))[1]
            return original(k,owner,default)
        self.binding.calls['GetValueOfAttribute']=read
    def alternative(self):
        return self.R.CashFormulaTrial('progress_money',2.,self.binding,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def primary_lane(self):
        b=self.bind()
        return self.R.Trial('progress_money',2.,b,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def test_generic_cycle(self):
        l=self.alternative();self.assertTrue(l.begin(),self.messages);self.tick(l);self.assertEqual(l.phase,'active',self.messages);self.assertEqual(self.values[self.generic][1],3.)
        l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(self.values[self.generic][1],1.5);self.assertEqual([c[0] for c in self.calls],[self.generic]*2)
    def test_existing_primary_preserved(self):
        lane=self.primary_lane();selected=self.R.choose_cash_trial(lane,lambda:self.fail('alternative called'))
        self.assertIs(selected,lane);self.assertFalse(self.calls)
    def test_primary_absent_fallback(self):
        del self.values[self.primary];lane=self.R.choose_cash_trial(self.primary_lane(),self.alternative)
        self.assertEqual(lane.name,self.generic);self.assertEqual(lane.phase,'armed',self.messages);self.assertFalse(self.calls)
        self.tick(lane);self.assertEqual(lane.phase,'active',self.messages);self.assertNotIn(self.primary,self.values)
    def test_no_generic_entry_creation(self):
        del self.values[self.generic];l=self.alternative();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_wrong_formula_value_no_write(self):
        self.override=123.;l=self.alternative();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_wrong_formula_type_no_write(self):
        self.formula_def.Value._type=t('wrong',self.R.ENGINE+'WrongResolver');l=self.alternative();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_level_drift_before_dispatch(self):
        l=self.alternative();self.assertTrue(l.begin());self.level=26.;self.tick(l);self.assertFalse(self.calls)
    def test_formula_no_change_restores_original_entry(self):
        l=self.alternative();self.assertTrue(l.begin());self.override=4*25*2*1.5;self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.generic][1],1.5);self.assertEqual(len(self.calls),2)
    def test_formula_unavailable_after_activation_restores(self):
        l=self.alternative();self.assertTrue(l.begin());self.tick(l);del self.defs.definitions[self.R.CASH_FORMULA];self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.generic][1],1.5);self.assertEqual(len(self.calls),2)
    def test_permission_loss_original_cleanup(self):
        l=self.alternative();self.assertTrue(l.begin());self.tick(l);self.ok=False;self.permission=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(self.values[self.generic][1],1.5)
    def test_no_fallback_after_armed_primary(self):
        l=self.primary_lane();self.assertTrue(l.begin());self.tick(l);self.assertIs(self.R.choose_cash_trial(l,lambda:self.fail('alternative called')),l);self.assertEqual(len(self.calls),1)
    def witnessed_primary(self):
        b=self.R.CashPrimaryBinding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
        b.calls['GetValueOfAttribute']=self.binding.calls['GetValueOfAttribute']
        return self.R.CashPrimaryTrial('progress_money',2.,b,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def test_primary_formula_cycle(self):
        l=self.witnessed_primary();self.assertTrue(l.begin(),self.messages);self.assertIsNotNone(l.formula_base)
        self.tick(l);self.assertEqual(l.phase,'active',self.messages);self.assertEqual(self.values[self.primary][1],4.)
        l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(self.values[self.primary][1],2.)
    def test_primary_legacy_without_formula(self):
        del self.defs.definitions[self.R.CASH_FORMULA];l=self.witnessed_primary();self.assertTrue(l.begin(),self.messages);self.assertIsNone(l.formula_base)
        self.tick(l);self.assertEqual(l.phase,'active',self.messages);l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages)
    def test_primary_formula_contradiction_no_dispatch(self):
        self.override=123.;l=self.witnessed_primary();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_primary_formula_nonresponsive_restores(self):
        l=self.witnessed_primary();self.assertTrue(l.begin());self.override=4*25*2*1.5
        self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.primary][1],2.);self.assertEqual(len(self.calls),2)
    def test_generic_natural_level_gain(self):
        l=self.alternative();self.assertTrue(l.begin());self.tick(l);self.level=26.;self.tick(l)
        self.assertEqual(l.phase,'active',self.messages);self.assertEqual(l.formula_level,26.);self.assertEqual(len(self.calls),1)
        l.stop('test');self.tick(l);self.level=27.;self.tick(l);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(len(self.calls),2)
    def test_primary_natural_level_gain(self):
        l=self.witnessed_primary();self.assertTrue(l.begin());self.tick(l);self.level=26.;self.tick(l)
        self.assertEqual(l.phase,'active',self.messages);l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages);self.assertEqual(len(self.calls),2)
    def test_level_decrease_not_admitted(self):
        l=self.alternative();self.assertTrue(l.begin());self.tick(l);self.level=24.;self.tick(l)
        self.assertTrue(l.fault);self.assertEqual(self.values[self.generic][1],1.5);self.assertEqual(len(self.calls),2)
    def test_primary_generic_peer_drift_restores(self):
        l=self.witnessed_primary();self.assertTrue(l.begin());self.tick(l);self.values[self.generic]=('Float',1.7);self.tick(l)
        self.assertTrue(l.fault);self.assertEqual(self.values[self.primary][1],2.);self.assertEqual(self.values[self.generic][1],1.7);self.assertEqual(len(self.calls),2)
    def test_primary_no_fallback_after_formula_attempt(self):
        l=self.witnessed_primary();self.assertTrue(l.begin());self.tick(l)
        self.assertIs(self.R.choose_cash_trial(l,lambda:self.fail('alternative called')),l);self.assertEqual(len(self.calls),1)
    def test_primary_zero_formula_not_unavailable(self):
        self.override=0.;l=self.witnessed_primary();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_primary_invalid_level_not_unavailable(self):
        self.level=25.5;l=self.witnessed_primary();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_primary_sentinel_formula_preserves_legacy(self):
        self.override=-123456.;l=self.witnessed_primary();self.assertTrue(l.begin(),self.messages);self.assertIsNone(l.formula_base)
        self.tick(l);self.assertEqual(l.phase,'active',self.messages);l.stop('test');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done',self.messages)
