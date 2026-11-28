"""Synthetic native gun expression and backend lifecycle tests."""
from test_gun_luck_r63 import GunTests
from test_combat_r13 import Node
from test_double_jump_r52 import p,t
from test_native_resource_rates import FGbxDefPtr,WrappedStruct

class GunFormulaTests(GunTests):
    def setUp(self):
        super().setUp();R=self.R
        actor=t('ActorContextResolver',R.ENGINE+'ActorContextResolver')
        et=t('GbxAttributeExpression',R.ENGINE+'GbxAttributeExpression')
        resolver=t('GbxExpressionValueResolver',R.ENGINE+'GbxExpressionValueResolver',p('Expression',R.S,Struct=et))
        self.formulas={R.GUN_ADDITIVE:None}
        for family in R.GUN_FAMILIES:
            peer='caused_damage_'+family+'_multiplier';self.values[peer]=('Float',1.25)
            self.formulas['calc_'+peer]=peer
        for name in self.formulas:
            self.defs.definitions[name]=Node(Context=Node(_type=actor),Value=Node(_type=resolver,Expression=Node(_type=et)))
        self.binding=R.GunFormulaBinding(self.fs,self.bound,lambda typ,Name:self.key(Name),FGbxDefPtr,self.defs,WrappedStruct)
        self.override={};old=self.binding.calls['GetValueOfAttribute']
        def read(k,owner,default):
            if k in self.override:return self.override[k]
            if k in self.formulas:
                peer=self.formulas[k];return self.values[R.GUN_KEY][1]-1.+(self.values[peer][1] if peer else 0.)
            return old(k,owner,default)
        self.binding.calls['GetValueOfAttribute']=read
    def witnessed(self,scale=2.,continuous=False):
        cls=self.R.SessionGunTrial if continuous else self.R.GunFormulaTrial
        return cls(self.R.GUN_MODE,scale,self.binding,lambda:(self.pc,self.pawn,self.state,self.ok),lambda o:lambda:o,lambda:self.time,lambda:self.tid,self.messages.append,lambda:self.permission)
    def test_families_apply_restore(self):
        l=self.witnessed();self.assertTrue(l.begin(),self.messages);self.tick(l);self.assertEqual(l.phase,'active',self.messages);self.assertEqual(self.values[l.name][1],2.);l.stop('off');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(self.values[l.name][1],1.)
    def test_reduced_additive_signed(self):
        l=self.witnessed(.5);self.assertTrue(l.begin());self.tick(l);self.assertEqual(l.phase,'active');self.assertEqual(self.binding.formula(self.pawn)[1],-.5);l.stop('off');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done')
    def test_family_missing(self):
        del self.defs.definitions['calc_caused_damage_smg_multiplier'];self.assertFalse(self.witnessed().begin());self.assertFalse(self.calls)
    def test_family_mismatch(self):
        self.override['calc_caused_damage_smg_multiplier']=7.;self.assertFalse(self.witnessed().begin());self.assertFalse(self.calls)
    def test_additive_missing(self):
        self.override[self.R.GUN_ADDITIVE]=-123456.;self.assertFalse(self.witnessed().begin());self.assertFalse(self.calls)
    def test_additive_nonresponse_rollback(self):
        l=self.witnessed();self.assertTrue(l.begin());self.override[self.R.GUN_ADDITIVE]=0.;self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[l.name][1],1.);self.assertEqual(len(self.calls),2)
    def test_peer_drift_restore(self):
        l=self.witnessed();l.begin();self.tick(l);self.values['caused_damage_smg_multiplier']=('Float',2.);self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[l.name][1],1.);self.assertEqual(self.values['caused_damage_smg_multiplier'][1],2.)
    def test_session_and_join_cleanup(self):
        l=self.witnessed(continuous=True);self.assertTrue(l.begin());self.tick(l);self.tick(l,100.);self.assertEqual(l.phase,'active');self.ok=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done');self.assertEqual(self.values[l.name][1],1.)
    def test_target_invalid(self):
        self.values['caused_damage_smg_multiplier']=('Float',.1);self.assertFalse(self.witnessed(.5).begin());self.assertFalse(self.calls)
    def test_backend_alias_disjoint(self):
        m=self.base.m;k='native_rate_gun_actor';o=m._PREVIEW_BY_KEY['damage'];f=m.AUTO_OPTIONS['damage'];self.assertIs(m.NATIVE_RATE_OPTIONS['gun_actor'],o);self.assertIs(m.NATIVE_AUTO_OPTIONS[k],f);self.assertEqual(sum(x is f for x in m.ALL),1);self.assertEqual(sum(x is o for x in m.ALL),1);f.value=True;o.value=2.;self.assertEqual(m.auto_desired()['damage'],2.);self.assertFalse(m.native_rate_allowed(k,2.));m.GUN_ACTOR_BACKEND.value=True;self.assertNotIn('damage',m.auto_desired());self.assertTrue(m.native_rate_allowed(k,2.))
    def test_backend_cleanup_before_field(self):
        m=self.base.m;k='native_rate_gun_actor';l=self.witnessed(continuous=True);l.begin();self.tick(l);m._automation_leases[k]=l;m._automation_attempted.add(k);m.automation_permitted=lambda:True;m.auto_master.value=True;m.AUTO_OPTIONS['damage'].value=True;m._PREVIEW_BY_KEY['damage'].value=2.;m.GUN_ACTOR_BACKEND.value=False;self.assertNotIn('damage',m.auto_desired());self.time+=.6;m.automation_tick();self.assertEqual(l.phase,'verify');self.assertNotIn('damage',m.auto_desired());self.time+=.6;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertEqual(m.auto_desired()['damage'],2.)
    def test_backend_switch_blocked(self):
        m=self.base.m;m.AUTO_OPTIONS['damage'].value=True;m.set_auto_setting(m.GUN_ACTOR_BACKEND,True);self.assertFalse(m.GUN_ACTOR_BACKEND.value)
    def test_cash_conflict(self):
        m=self.base.m;m.GUN_ACTOR_BACKEND.value=True;m.AUTO_OPTIONS['damage'].value=True;m._PREVIEW_BY_KEY['damage'].value=2.
        cash=m.NATIVE_AUTO_OPTIONS['native_rate_cash'];cash.value=True;m._PREVIEW_BY_KEY['progress_money'].value=2.
        self.assertFalse(m.native_rate_allowed('native_rate_gun_actor',2.));self.assertFalse(m.native_rate_allowed('native_rate_cash',2.))
        cash.value=False;self.assertTrue(m.native_rate_allowed('native_rate_gun_actor',2.));cash.value=True;m.AUTO_OPTIONS['damage'].value=False;self.assertTrue(m.native_rate_allowed('native_rate_cash',2.))
        m._automation_leases['native_rate_gun_actor']=object();self.assertFalse(m.native_rate_allowed('native_rate_cash',2.))
    def test_backend_factory(self):
        m=self.base.m;m._PREVIEW_BY_KEY['damage'].value=.5;seen=[];m.make_session_gun=lambda session,scale:seen.append((session,scale)) or 'gun';self.assertEqual(m.make_automation_lane('native_rate_gun_actor','scope'),'gun');self.assertEqual(seen,[('scope',.5)])

from test_f8_simple import SimpleF8
class GunFormulaUI(SimpleF8):
    def test_backend_ui(self):
        m=self.m;m._category=0;flag=m.GUN_ACTOR_BACKEND;label=flag.display_name+'##'+flag.identifier
        self.assertIn(label,self.render());self.render({label:True});self.assertTrue(flag.value);self.assertFalse(m.AUTO_OPTIONS['damage'].value)
        self.render({'Damage multiplier##damage':2.,m.AUTO_OPTIONS['damage'].display_name+'##'+m.AUTO_OPTIONS['damage'].identifier:True});self.assertTrue(m.AUTO_OPTIONS['damage'].value);self.assertNotIn('damage',m.auto_desired());self.render(clicks=['Restore All']);self.assertFalse(m.AUTO_OPTIONS['damage'].value)
