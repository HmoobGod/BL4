"""Synthetic Vault Power scope, independent tooltip witnesses, persistent lifecycle."""
import unittest
from test_native_resource_rates import NativeRateTests, Modifier
from test_combat_r13 import Node, desc
from test_double_jump_r52 import p,t
from test_health_pulse_r17 import FGameDataHandle

class VaultRateTests(unittest.TestCase):
    def setUp(self):
        self.n=NativeRateTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
        n=self.n;self.R=n.R;n.local_health();n.pc.Pawn=n.pawn
        self.vs=Node(_type=t('VaultPowerState','/Script/OakGame.VaultPowerState'))
        self.comp=Node(Class=t('OakCharacterMovementComponent','/Script/OakGame.OakCharacterMovementComponent',desc('VaultPowerState',self.vs._type)),OakCharacterOwner=n.pawn,VaultPowerState=self.vs)
        n.pawn.CharacterMovement=self.comp
        self.resource=FGameDataHandle('Vault_Power','Other','Other');self.resource._type_handle=5
        self.peers={};self.peer_delta=0.
        for mode in self.R.VAULT_MODES:
            d=n.attr.definitions[self.R.TARGETS[mode][0]];d.Context.ResourceDef=self.resource
        for mode,name in self.R.VAULT_TOOLTIP.items():
            c=Node(_type=t('GameResourcePoolContextResolver',self.R.HEALTH_CONTEXT,p('ResourceDef','ZGameDataHandleProperty',TypeHandle=5)),ResourceDef=self.resource)
            v=Node(_type=t('GameResourcePoolValueResolver','/Script/GbxGame.GameResourcePoolValueResolver',p('ResourceDef','ZGameDataHandleProperty',TypeHandle=5),p('ValueType','ZEnumProperty',Enum=Node(Name='/Script/GbxGame.EGameResourcePoolValueType'))),ResourceDef=self.resource,ValueType=Node(name=self.R.TARGETS[mode][1]))
            n.attr.definitions[name]=Node(Context=c,Value=v);self.peers[mode]=4.
        def read(name,pawn,default):
            self.assertIs(pawn,n.pawn)
            for m in self.R.VAULT_MODES:
                if name==self.R.TARGETS[m][0]:return n.rate if n.mode==m else self.peers[m]
                if self.R.VAULT_TOOLTIP.get(m)==name:return (n.rate if n.mode==m else self.peers[m])+self.peer_delta
            raise ValueError('unexpected reader')
        n.binding.calls['GetValueOfAttribute']=read
    def lane(self,mode='vaultregen',selection=2.):
        n=self.n;n.resolve=self.R.make_local_resolver(mode,n.binding,lambda:(n.pc,n.pawn,n.world,n.allowed),FGameDataHandle,(lambda pawn,h:n.native_cur,lambda pawn,h:n.native_pct,5))
        n.mode=mode;n.rate=n.base_rate=4.
        lane=self.R.NativeRateTrial(mode,n.binding,n.resolve,lambda x:lambda:x,lambda:n.now,lambda:n.tid,n.msg.append,lambda:n.allowed,lambda key:self.R.original_pool_identity(mode,key),selection=selection,continuous=True)
        return lane
    def arm(self,mode='vaultregen',expected=8.):
        n=self.n;l=self.lane(mode);self.assertTrue(l.begin(),n.msg);n.tick(l);self.assertEqual(l.phase,'active',n.msg);self.assertEqual(n.rate,expected);return l
    def restore(self,l):
        n=self.n;l.stop('test');n.tick(l);n.tick(l);self.assertEqual(l.phase,'done',n.msg);self.assertEqual(n.rate,4.);self.assertEqual([x[0] for x in n.native],['add','remove'])
    def test_rate(self):self.restore(self.arm())
    def test_delay(self):self.restore(self.arm('vaultdelay',2.))
    def test_depleted_delay(self):self.restore(self.arm('vaultdepleted',2.))
    def test_persistent_no_timeout(self):
        l=self.arm();self.n.tick(l,60.);self.assertEqual(l.phase,'active');self.restore(l)
    def test_initial_empty_refused(self):
        self.n.native_cur=self.n.native_pct=0.;self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_later_depletion(self):
        l=self.arm();self.n.native_cur=self.n.native_pct=0.;self.n.tick(l,.3);self.assertEqual(l.phase,'active');self.restore(l)
    def test_foreign_movement_owner(self):
        self.comp.OakCharacterOwner=Node();self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_wrong_controller_pawn(self):
        self.n.pc.Pawn=Node();self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_tooltip_mismatch(self):
        self.peer_delta=.2;self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_tooltip_selector_mismatch(self):
        self.n.attr.definitions[self.R.VAULT_TOOLTIP['vaultregen']].Value.ValueType=Node(name='MaxValue');self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_wrong_resource(self):
        self.resource._name='Shield';self.assertFalse(self.lane().begin());self.assertFalse(self.n.native)
    def test_scope_change_before_add(self):
        l=self.lane();self.assertTrue(l.begin());self.comp.VaultPowerState=Node(_type=self.vs._type);self.n.tick(l);self.assertFalse(self.n.native)
    def test_permission_loss_restores(self):
        l=self.arm();self.n.allowed=False;self.n.tick(l,permit=False);self.n.tick(l,permit=False);self.assertEqual(l.phase,'done',self.n.msg);self.assertEqual(self.n.rate,4.)
    def test_inferred_max_drift_removes(self):
        l=self.arm();self.n.native_cur=80.;self.n.tick(l,.3);self.assertEqual([x[0] for x in self.n.native],['add','remove']);self.assertTrue(l.fault)
    def test_independent_peer_change_not_pinned(self):
        l=self.arm();self.peers['vaultdelay']=2.;self.n.tick(l,.3);self.assertEqual(l.phase,'active',self.n.msg);self.restore(l)
    def test_option_independent(self):
        m=self.n.base.m
        for mode in self.R.VAULT_MODES:
            k='native_rate_'+mode;self.assertFalse(m.native_rate_allowed(k,2.));m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS[mode].value=2.;self.assertTrue(m.native_rate_allowed(k,2.))
        m.NATIVE_AUTO_OPTIONS['native_rate_vaultregen'].value=False
        self.assertFalse(m.native_rate_allowed('native_rate_vaultregen',2.));self.assertTrue(m.native_rate_allowed('native_rate_vaultdelay',2.))

class PassiveShieldRateTests(unittest.TestCase):
    def setUp(self):
        self.n=NativeRateTests();self.n.setUp();self.addCleanup(self.n.doCleanups)
    def lane(self):
        n=self.n;n.shield_pool_trial('shieldpassive',0.,2.)
        return n.R.NativeRateTrial('shieldpassive',n.binding,n.resolve,lambda x:lambda:x,lambda:n.now,lambda:n.tid,n.msg.append,lambda:n.allowed,lambda key:n.R.original_pool_identity('shieldpassive',key),selection=2.,continuous=True)
    def test_passive_from_zero_and_restore(self):
        n=self.n;l=self.lane();self.assertTrue(l.begin(),n.msg);n.tick(l);self.assertEqual(l.phase,'active',n.msg);self.assertEqual(n.rate,.002)
        self.assertEqual(n.native,[('add','shield_resource_passive_pct_regen',Modifier.PostAdd,.002)])
        n.tick(l,60.);self.assertEqual(l.phase,'active');l.stop('test');n.tick(l);n.tick(l);self.assertEqual(l.phase,'done',n.msg);self.assertEqual(n.rate,0.)
    def test_shield_scope_loss_before_add(self):
        n=self.n;l=self.lane();self.assertTrue(l.begin());n.shield.OwningCharacter=Node();n.tick(l);self.assertFalse(n.native)
    def test_depletion_while_active(self):
        n=self.n;l=self.lane();self.assertTrue(l.begin());n.tick(l);n.set_shield_charge(0.);n.tick(l,.3);self.assertEqual(l.phase,'active');l.stop('test');n.tick(l);n.tick(l);self.assertEqual(l.phase,'done',n.msg)
    def test_shield_assist_conflict(self):
        m=self.n.base.m;k='native_rate_shieldpassive';m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['shieldpassive'].value=2.
        self.assertTrue(m.native_rate_allowed(k,2.));self.assertIn('choose native',m.recovery_conflict('shield'))
        m.AUTOMATION_OPTIONS['shield'].value=True;self.assertFalse(m.native_rate_allowed(k,2.))
    def test_existing_shield_field_conflict(self):
        m=self.n.base.m;k='native_rate_shieldpassive';m.NATIVE_AUTO_OPTIONS[k].value=True;m.NATIVE_RATE_OPTIONS['shieldpassive'].value=2.
        m.AUTO_OPTIONS['shield_regen_rate'].value=True;m._PREVIEW_BY_KEY['shield_regen_rate'].value=2.
        self.assertFalse(m.native_rate_allowed(k,2.))
