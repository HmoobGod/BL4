"""Both existing native leases sharing a peer witness; synthetic, not game execution."""
import unittest
from test_gun_formula_session import GunFormulaTests
from test_combat_r13 import Node
from test_double_jump_r52 import p,t
from test_native_resource_rates import FGbxDefPtr,WrappedStruct

class CashGunIntegration(GunFormulaTests):
    def setUp(self):
        super().setUp(); R=self.R; m=self.base.m
        self.primary=R.TARGETS['progress_money'];self.generic=R.CASH_GENERIC
        self.values[self.generic]=('Float',1.5)
        self.defs.definitions[self.generic]=Node(Context=Node(_type=self.ctx),Value=Node(_type=self.val,Variable=self.key(self.generic)))
        actor=t('ActorContextResolver',R.ENGINE+'ActorContextResolver')
        et=t('GbxAttributeExpression',R.ENGINE+'GbxAttributeExpression')
        resolver=t('GbxExpressionValueResolver',R.ENGINE+'GbxExpressionValueResolver',p('Expression',R.S,Struct=et))
        self.defs.definitions[R.CASH_FORMULA]=Node(Context=Node(_type=actor),Value=Node(_type=resolver,Expression=Node(_type=et)))
        self.m=m; self.ck=m.CASH_LANE;self.gk=m.ACTOR_GUN_LANE
        m.auto_master.value=True;m.auto_consent.value=True;m.GUN_ACTOR_BACKEND.value=True;m.AUTO_OPTIONS['damage'].value=True
        m._PREVIEW_BY_KEY['damage'].value=2.;m._PREVIEW_BY_KEY['progress_money'].value=2.
        m.NATIVE_AUTO_OPTIONS[self.ck].value=True
        m.automation_permitted=lambda:self.permission and not m.automation_fault()
        self.advance_count=0
    def cash(self,primary=True):
        R=self.R
        cls=R.SessionCashPrimary if primary else R.SessionCashGeneric
        b=(R.CashPrimaryBinding if primary else R.CashFormulaBinding)(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
        original=b.calls['GetValueOfAttribute']
        def read(k,owner,default):
            if k==R.CASH_LEVEL:return 25.
            if k==R.CASH_FORMULA:return 100.*self.values[self.primary][1]*self.values[self.generic][1]
            return original(k,owner,default)
        b.calls['GetValueOfAttribute']=read
        return cls('progress_money',2.,b,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission and self.m.native_rate_allowed(self.ck,2.))
    def add_cash(self,primary=True):
        cash=self.cash(primary);self.m._automation_leases[self.ck]=cash;self.m._automation_attempted.add(self.ck)
        self.assertTrue(cash.begin(),self.messages);self.tick(cash);self.assertEqual(cash.phase,'active',self.messages);return cash
    def add_gun(self):
        gun=self.witnessed(continuous=True);gun.permission=lambda:self.permission and self.m.native_rate_allowed(self.gk,2.)
        self.m._automation_leases[self.gk]=gun;self.m._automation_attempted.add(self.gk)
        self.assertTrue(gun.begin(),self.messages);self.tick(gun);self.assertEqual(gun.phase,'active',self.messages);return gun
    def both(self,primary=True):return self.add_cash(primary),self.add_gun()
    def advance(self,dt=.6):
        self.time+=dt;self.m.automation_tick()
    def assert_values(self,cash,gun):
        self.assertEqual(self.values[self.primary][1],cash);self.assertEqual(self.values[self.R.GUN_KEY][1],gun)
    def test_joint_primary_activation(self):
        self.assertFalse(self.m.native_rate_allowed(self.gk,2.));cash,gun=self.both();self.advance()
        self.assert_values(4.,2.);self.assertEqual((cash.phase,gun.phase),('active','active'));self.assertEqual(len(self.calls),2)
    def test_joint_generic_activation(self):
        cash,gun=self.both(False);self.advance();self.assert_values(2.,2.);self.assertEqual(self.values[self.generic][1],3.)
        self.m.NATIVE_AUTO_OPTIONS[self.ck].value=False;self.advance();self.assertEqual(gun.phase,'verify');self.assertEqual(self.values[self.generic][1],3.);self.advance();self.advance();self.assertEqual((cash.phase,gun.phase),('done','done'));self.assertEqual(self.values[self.generic][1],1.5)
    def test_cash_disable_order(self):
        cash,gun=self.both();self.m.NATIVE_AUTO_OPTIONS[self.ck].value=False
        self.advance();self.assertEqual((cash.phase,gun.phase),('active','verify'));self.assert_values(4.,1.)
        self.advance();self.assertEqual((cash.phase,gun.phase),('verify','done'));self.assert_values(2.,1.)
        self.advance();self.assertEqual(cash.phase,'done');self.assertFalse(self.m._automation_leases);self.assertEqual([c[0] for c in self.calls],[self.primary,self.R.GUN_KEY,self.R.GUN_KEY,self.primary]);self.assertIn(self.gk,self.m._automation_attempted)
    def test_gun_off_cash_retained(self):
        cash,gun=self.both();self.m.AUTO_OPTIONS['damage'].value=False;self.advance();self.advance();self.assertEqual(gun.phase,'done');self.assertEqual(cash.phase,'active');self.assert_values(4.,1.);self.assertEqual(len(self.calls),3)
    def test_cash_edit_drains_both(self):
        cash,gun=self.both();self.m._PREVIEW_BY_KEY['progress_money'].value=3.;cash.next_selection=3.
        self.advance();self.assert_values(4.,1.);self.advance();self.advance();self.assert_values(2.,1.);self.assertFalse(self.m._automation_leases);self.assertTrue({self.ck,self.gk}<=self.m._automation_attempted)
    def test_permission_loss_order(self):
        cash,gun=self.both();self.permission=False;self.ok=False
        self.advance();self.assertEqual((cash.phase,gun.phase),('active','verify'));self.assert_values(4.,1.)
        self.advance();self.advance();self.assertEqual((cash.phase,gun.phase),('done','done'));self.assert_values(2.,1.);self.assertFalse(self.m.automation_fault())
    def test_pending_cash_drains_existing_gun(self):
        self.m.NATIVE_AUTO_OPTIONS[self.ck].value=False;gun=self.add_gun();self.m.NATIVE_AUTO_OPTIONS[self.ck].value=True
        self.assertFalse(self.m.native_rate_allowed(self.ck,2.));self.advance();self.assertEqual(gun.phase,'verify');self.assertFalse(self.m.native_rate_allowed(self.ck,2.));self.advance();self.assertEqual(gun.phase,'done');self.assertTrue(self.m.native_rate_allowed(self.ck,2.));self.assertIn(self.gk,self.m._automation_attempted)
    def test_neutral_or_held_cash_does_not_block_gun(self):
        self.m._PREVIEW_BY_KEY['progress_money'].value=1.;self.assertTrue(self.m.native_rate_allowed(self.gk,2.))
        self.m._PREVIEW_BY_KEY['progress_money'].value=2.;self.assertFalse(self.m.native_rate_allowed(self.gk,2.));self.m._automation_attempted.add(self.ck);self.assertTrue(self.m.native_rate_allowed(self.gk,2.))
    def test_armed_cash_waits(self):
        cash=self.cash();self.m._automation_leases[self.ck]=cash;self.assertTrue(cash.begin());self.assertFalse(self.m.native_rate_allowed(self.gk,2.));self.tick(cash);self.assertTrue(self.m.native_rate_allowed(self.gk,2.))
    def test_cash_foreign_drift_does_not_overwrite(self):
        cash,gun=self.both();self.values[self.primary]=('Float',7.);self.advance();self.advance();self.advance()
        self.assertTrue(cash.fault or gun.fault);self.assertEqual(self.values[self.primary][1],7.);self.assertEqual(self.values[self.R.GUN_KEY][1],1.)
    def test_scope_witness(self):
        cash,gun=self.both()
        import threading
        cash.thread=threading.get_ident;gun.thread=threading.get_ident
        cash.record=(*cash.record[:2],threading.get_ident(),cash.record[3]);gun.record=(*gun.record[:2],threading.get_ident(),gun.record[3])
        self.assertTrue(self.m.cooperating_cash_scope(gun,cash))
        cash.board_key=('different',0)
        with self.assertRaises(ValueError):self.m.cooperating_cash_scope(gun,cash)
    def test_master_stop_drains_in_order(self):
        cash,gun=self.both();self.m.stop_automation('Restore All');self.advance();self.assertEqual((cash.phase,gun.phase),('active','verify'));self.advance();self.advance();self.assert_values(2.,1.);self.assertFalse(self.m._automation_leases)
    def test_scope_loss_without_global_permission_loss(self):
        cash,gun=self.both();self.ok=False
        self.advance();self.assertEqual((cash.phase,gun.phase),('active','verify'));self.assert_values(4.,1.)
        self.advance();self.advance();self.assertEqual((cash.phase,gun.phase),('done','done'));self.assert_values(2.,1.);self.assertFalse(self.m.automation_fault())
    def test_cash_permission_before_due_orders_cleanup(self):
        cash,gun=self.both();cash.permission=lambda:False
        self.advance(.01);self.assertEqual((cash.phase,gun.phase),('active','verify'));self.assert_values(4.,1.)
        self.advance();self.advance();self.assert_values(2.,1.);self.assertFalse(self.m.automation_fault())
    def test_no_new_cash_scope_reads_on_fast_frame(self):
        cash,gun=self.both();self.advance();seen=[];orig=cash.scope
        cash.scope=lambda:seen.append(True) or orig()
        self.advance(.01);self.assertFalse(seen);self.assertEqual((cash.phase,gun.phase),('active','active'));self.assert_values(4.,2.)
