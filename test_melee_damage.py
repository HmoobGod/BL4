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


class SessionMeleeTests(MeleeDamageTests):
    def session(self,scale=2.):
        old=self.trial(scale)
        return self.R.SessionMeleeTrial(old.mode,old.scale,old.binding,old.context,old.weak,old.clock,old.thread,old.report,old.permission)

    def enable(self,scale=2.):
        m=self.base.m;k=m.MELEE_LANE;m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['melee'].value=scale
        m.auto_master.value=True;m.automation_permitted=lambda:self.permission and not m.automation_fault()
        return m,k

    def add(self,scale=2.):
        m,k=self.enable(scale);l=self.session(scale)
        l.permission=lambda:self.permission and m.native_rate_allowed(k,scale)
        m._automation_leases[k]=l;m._automation_attempted.add(k)
        self.assertTrue(l.begin(),self.messages);self.tick(l);self.assertEqual(l.phase,'active',self.messages)
        return m,k,l

    def advance(self,m):
        self.time+=.6;m.automation_tick()

    def test_session_independent_lifetime(self):
        m,k,l=self.add(.5);self.tick(l,120.);self.assertEqual(l.phase,'active');self.assertEqual(self.values[self.keyname][1],.5)
        self.assertEqual(self.values[self.R.GUN_KEY][1],1.);self.assertEqual(len(self.calls),1)
        m.NATIVE_AUTO_OPTIONS[k].value=False;self.advance(m);self.assertEqual(l.phase,'verify');self.advance(m)
        self.assertEqual(l.phase,'done');self.assertEqual(self.values[self.keyname][1],1.);self.assertNotIn(k,m._automation_leases)

    def test_cash_waits_for_delayed_melee_restore(self):
        m,k,l=self.add();m.NATIVE_AUTO_OPTIONS[m.CASH_LANE].value=True;m.NATIVE_RATE_OPTIONS['cash'].value=2.
        self.assertFalse(m.native_rate_allowed(m.CASH_LANE,2.));self.advance(m);self.assertEqual(l.phase,'verify')
        self.assertFalse(m.native_rate_allowed(m.CASH_LANE,2.));self.advance(m);self.assertEqual(l.phase,'done')
        self.assertTrue(m.native_rate_allowed(m.CASH_LANE,2.));self.assertIn(k,m._automation_attempted);self.assertEqual([c[0] for c in self.calls],[self.keyname]*2)

    def test_actor_gun_waits_for_delayed_melee_restore(self):
        m,k,l=self.add();m.GUN_ACTOR_BACKEND.value=True;m.AUTO_OPTIONS['damage'].value=True;m._PREVIEW_BY_KEY['damage'].value=2.
        self.assertFalse(m.native_rate_allowed(m.ACTOR_GUN_LANE,2.));self.advance(m);self.assertEqual(l.phase,'verify')
        self.assertFalse(m.native_rate_allowed(m.ACTOR_GUN_LANE,2.));self.advance(m);self.assertEqual(l.phase,'done');self.assertTrue(m.native_rate_allowed(m.ACTOR_GUN_LANE,2.))

    def test_melee_does_not_disturb_equipped_field_gun(self):
        m,k=self.enable();m.AUTO_OPTIONS['damage'].value=True;m._PREVIEW_BY_KEY['damage'].value=3.
        self.assertTrue(m.native_rate_allowed(k,2.));self.assertEqual(m.auto_desired()['damage'],3.)
        m.GUN_ACTOR_BACKEND.value=True;self.assertFalse(m.native_rate_allowed(k,2.))

    def test_existing_cash_or_actor_gun_blocks_melee(self):
        m,k=self.enable()
        for peer in (m.CASH_LANE,m.ACTOR_GUN_LANE):
            m._automation_leases[peer]=Node(record=object(),fault=False)
            self.assertFalse(m.native_rate_allowed(k,2.));m._automation_leases.clear()
        self.assertTrue(m.native_rate_allowed(k,2.))

    def test_session_selection_edit_no_implicit_rearm(self):
        m,k,l=self.add();m.NATIVE_RATE_OPTIONS['melee'].value=3.;l.next_selection=3.
        self.advance(m);self.assertEqual(l.phase,'verify');self.advance(m)
        self.assertEqual(l.phase,'done');self.assertNotIn(k,m._automation_leases);self.assertIn(k,m._automation_attempted);self.assertEqual(len(self.calls),2)

    def test_session_join_restores(self):
        m,k,l=self.add();self.ok=False;self.permission=False;self.advance(m);self.advance(m)
        self.assertEqual(l.phase,'done',self.messages);self.assertEqual(self.values[self.keyname][1],1.);self.assertFalse(l.fault)

    def test_session_formula_fault_stops(self):
        m,k,l=self.add();self.override=42.;self.advance(m)
        self.assertTrue(l.fault);self.assertEqual(self.values[self.keyname][1],1.);self.assertTrue(m.automation_fault())

    def test_independent_options_and_factory(self):
        m=self.base.m;k=m.MELEE_LANE;o=m.NATIVE_RATE_OPTIONS['melee'];f=m.NATIVE_AUTO_OPTIONS[k]
        self.assertFalse(f.value);self.assertEqual(o.value,1.);self.assertEqual((o.min_value,o.max_value),(.5,5.));self.assertIsNot(o,m._PREVIEW_BY_KEY['damage']);self.assertEqual(sum(x is o for x in m.ALL),1);self.assertEqual(sum(x is f for x in m.ALL),1)
        seen=[];o.value=3.;m.make_session_melee=lambda session,scale:seen.append((session,scale)) or 'melee';self.assertEqual(m.make_automation_lane(k,'scope'),'melee');self.assertEqual(seen,[('scope',3.)])

from test_f8_simple import SimpleF8
class SessionMeleeUI(SimpleF8):
    def test_melee_f8_control_independent(self):
        m=self.m;m._category=0;f=m.NATIVE_AUTO_OPTIONS[m.MELEE_LANE];o=m.NATIVE_RATE_OPTIONS['melee']
        label=f.display_name+'##'+f.identifier;slider=o.display_name+'##'+o.identifier
        labels=self.render();self.assertIn(label,labels);self.assertIn(slider,labels)
        self.render({slider:2.5,label:True});self.assertEqual(o.value,2.5);self.assertTrue(f.value);self.assertEqual(m._PREVIEW_BY_KEY['damage'].value,1.);self.assertFalse(m.AUTO_OPTIONS['damage'].value)
        self.render(clicks=['Restore All']);self.assertFalse(f.value);self.assertFalse(m.auto_master.value)
