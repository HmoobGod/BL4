"""Synthetic persistent skill and live recovery controls, not game evidence."""
import unittest
from test_skill_pulse_r19 import SkillPulseTests
from test_recovery_r34 import ContinuousRecovery

class PersistentSkill(unittest.TestCase):
    def setUp(self):
        self.s=SkillPulseTests();self.s.setUp();self.addCleanup(self.s.doCleanups);self.m=self.s.m
    def arm(self,*modes,**settings):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**{'persistent_automation_skill_'+k:True for k in modes},**settings})
        for _ in range(4):self.s.advance(dt=.3)
    def test_default_off(self):
        self.arm();self.s.advance(.3,.7);self.s.advance(.4,.6);self.assertEqual(self.s.calls,[])
    def test_cooldown_continuous(self):
        self.arm('cooldown');self.s.advance(.3,dt=31);self.s.advance(.4);self.assertEqual(len(self.s.calls),1);self.assertEqual(self.s.calls[0][0],0)
    def test_duration_continuous(self):
        self.arm('duration');self.s.advance(d=.7,dt=31);self.s.advance(d=.6);self.assertEqual(len(self.s.calls),1);self.assertEqual(self.s.calls[0][0],1)
    def test_both_independent_with_jump(self):
        self.arm('cooldown','duration',persistent_jump=True,jump=1.5);self.s.advance(.3,.7);self.s.advance(.4,.6);self.assertEqual([c[0] for c in self.s.calls],[0,1]);self.assertIn('jump',self.m._controller.records)
    def test_disable_one(self):
        self.arm('cooldown','duration');self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['skill_cooldown'],False);self.s.advance(.3,.7);self.s.advance(.4,.6);self.assertEqual([c[0] for c in self.s.calls],[1])
    def test_charge_refused(self):
        self.s.d.ChargeComponentID=self.s.g;self.arm('cooldown');self.assertNotIn('skill_cooldown',self.m._automation_leases);self.s.advance(.3);self.s.advance(.4);self.assertEqual(self.s.calls,[])
    def test_join(self):
        self.arm('cooldown');self.s.advance(.3);self.s.b.f.players=2;self.s.advance(.4);self.assertEqual(self.s.calls,[]);self.assertFalse(self.m._automation_leases)
    def test_no_retry_on_scope_change(self):
        self.arm('cooldown');self.s.advance(.3);self.s.skills=[];self.s.advance(.4);self.assertFalse(self.m._automation_leases);self.s.skills=[self.s.skill];self.s.advance(.5);self.s.advance(.6);self.assertEqual(self.s.calls,[])
    def test_fault_stops_peer(self):
        self.arm('cooldown','duration');lease=self.m._automation_leases['skill_cooldown'];lease.api=(*lease.api[:3],lambda *a:(_ for _ in ()).throw(RuntimeError('uncertain')));self.s.advance(.3,.7);self.s.advance(.4,.6);self.assertTrue(self.m.automation_fault());self.assertNotIn('skill_duration',self.m._automation_leases);self.assertEqual(self.s.calls,[])
    def test_reentrant_disable(self):
        self.arm('cooldown');lease=self.m._automation_leases['skill_cooldown'];old=lease.api[0];self.s.advance(.3)
        def read(*a):
            result=old(*a);self.m.set_auto_setting(self.m.AUTOMATION_OPTIONS['skill_cooldown'],False);return result
        lease.api=(read,*lease.api[1:]);self.s.advance(.4);self.assertEqual(self.s.calls,[])

class RecoveryRates(unittest.TestCase):
    def setUp(self):
        self.r=ContinuousRecovery();self.r.setUp();self.addCleanup(self.r.doCleanups);self.m=self.r.m
    def test_independent_rates(self):
        self.r.arm('health','shield',recovery_rate_health=.3,recovery_rate_shield=.7);self.r.shield._values['Value']=55.;self.r.tick();self.r.shield._values['Value']=60.;self.r.tick();self.assertTrue(any(k=='health' and abs(a-.003)<1e-9 for k,a in self.r.calls));self.assertTrue(any(k=='shield' and abs(a-.007)<1e-9 for k,a in self.r.calls))
    def test_live_commit_without_restart(self):
        self.r.arm('health');lease=self.m._automation_leases['health'];self.r.tick();self.m.apply({'recovery_rate_health':.4});self.r.tick();self.assertIs(lease,self.m._automation_leases['health']);self.assertAlmostEqual(self.r.calls[-1][1],.004)
    def test_draft_not_applied(self):
        self.r.arm('health');self.m.queue_auto_edit(self.m.RECOVERY_RATES['health'],.2);self.r.tick();self.assertAlmostEqual(self.r.calls[-1][1],.01);self.m.flush_auto_edits(force=True);self.r.tick();self.assertAlmostEqual(self.r.calls[-1][1],.002)
    def test_rate_validation(self):
        self.r.arm('health');lease=self.m._automation_leases['health'];
        for value in (0,1.1,float('nan'),True):
            with self.assertRaises(ValueError):lease.update_rate(value)
        self.assertEqual(lease.fraction,.01)
    def test_rate_does_not_arm(self):
        self.r.arm(recovery_rate_health=.5,recovery_rate_shield=.4);self.r.tick();self.assertEqual(self.r.calls,[])
