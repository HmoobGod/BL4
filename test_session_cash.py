"""Synthetic session cash integration, not native gameplay certification."""
from test_cash_formula import CashFormulaTests

class SessionCashTests(CashFormulaTests):
    def session(self,primary=True):
        if primary:
            lane=self.witnessed_primary()
            cls=self.R.SessionCashPrimary
        else:
            lane=self.alternative()
            cls=self.R.SessionCashGeneric
        return cls(lane.mode,lane.scale,lane.binding,lane.context,lane.weak,lane.clock,lane.thread,lane.report,lane.permission)
    def test_session_lifetime_and_restore(self):
        l=self.session();self.assertTrue(l.begin());self.tick(l);self.tick(l,100.)
        self.assertEqual(l.phase,'active');self.assertEqual(self.values[self.primary][1],4.)
        l.stop('off');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done');self.assertEqual(self.values[self.primary][1],2.);self.assertEqual(len(self.calls),2)
    def test_generic_session(self):
        l=self.session(False);self.assertTrue(l.begin());self.tick(l);self.tick(l,100.);self.assertEqual(l.phase,'active');l.stop('off');self.tick(l);self.tick(l);self.assertEqual(self.values[self.generic][1],1.5)
    def test_formula_required(self):
        del self.defs.definitions[self.R.CASH_FORMULA];l=self.session();self.assertFalse(l.begin());self.assertFalse(self.calls)
    def test_session_formula_drift(self):
        l=self.session();l.begin();self.tick(l);self.override=42.;self.tick(l);self.assertTrue(l.fault);self.assertEqual(self.values[self.primary][1],2.)
    def test_session_level_gain(self):
        l=self.session();l.begin();self.tick(l);self.level+=1;self.tick(l,60.);self.assertEqual(l.phase,'active');l.stop('off');self.tick(l);self.tick(l);self.assertEqual(l.phase,'done')
    def test_session_permission_loss(self):
        l=self.session();l.begin();self.tick(l);self.ok=False;self.permission=False;self.tick(l,permit=False);self.tick(l,permit=False);self.assertEqual(l.phase,'done');self.assertEqual(self.values[self.primary][1],2.)
    def test_session_no_implicit_rearm(self):
        l=self.session();l.begin();self.tick(l);orig=l.record;l.stop('edit');self.tick(l);self.tick(l);self.assertFalse(l.rearm_verified(orig,3.));self.assertEqual(len(self.calls),2)
    def test_saved_cash_flag(self):
        m=self.base.m;k='native_rate_cash';o=m._PREVIEW_BY_KEY['progress_money'];self.assertIs(m.NATIVE_RATE_OPTIONS['cash'],o);self.assertEqual(sum(x is o for x in m.ALL),1);self.assertIn(o,m._COMPACT_OPTIONS[1]);self.assertFalse(m.NATIVE_AUTO_OPTIONS[k].value);self.assertFalse(m.native_rate_allowed(k,2.));m.NATIVE_AUTO_OPTIONS[k].value=True;o.value=2.;self.assertTrue(m.native_rate_allowed(k,2.));self.assertFalse(m.native_rate_allowed(k,3.))
    def test_stop_retains_cleanup(self):
        m=self.base.m;k='native_rate_cash';l=self.session();l.begin();self.tick(l);m._automation_leases[k]=l;m._automation_attempted.add(k);m.automation_permitted=lambda:False;m.stop_automation_lane(k,'off');self.assertIs(m._automation_leases[k],l);self.time+=.6;m.automation_tick();self.assertEqual(l.phase,'verify');self.time+=.6;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertEqual(self.values[self.primary][1],2.)
    def test_edit_drains_without_rearm(self):
        m=self.base.m;k='native_rate_cash';l=self.session();l.begin();self.tick(l);m._automation_leases[k]=l;m._automation_attempted.add(k);m.automation_permitted=lambda:True;m.auto_master.value=True;m.NATIVE_AUTO_OPTIONS[k].value=True;m._PREVIEW_BY_KEY['progress_money'].value=3.;l.next_selection=3.;self.time+=.6;m.automation_tick();self.assertEqual(l.phase,'verify');self.time+=.6;m.automation_tick();self.assertNotIn(k,m._automation_leases);self.assertEqual(self.values[self.primary][1],2.);self.assertEqual(len(self.calls),2)

from test_f8_simple import SimpleF8
class SessionCashUI(SimpleF8):
    def test_cash_compact_and_toggle(self):
        m=self.m;m._category=1;m._compact_view=True
        f=m.NATIVE_AUTO_OPTIONS['native_rate_cash'];label=f.display_name+'##'+f.identifier
        labels=self.render();self.assertIn(label,labels);self.assertIn('Money##progress_money',labels)
        self.assertTrue(any('Test earned Money' in x for x in labels));self.assertFalse(any('Test earned Enemy kill XP' in x for x in labels))
        self.render({'Money##progress_money':2.,label:True});self.assertTrue(m.auto_master.value);self.assertTrue(f.value);self.assertEqual(m._PREVIEW_BY_KEY['progress_money'].value,2.)
        self.render(clicks=['Restore All']);self.assertFalse(f.value);self.assertFalse(m.auto_master.value)
    def test_cash_factory_route(self):
        m=self.m;f=m.NATIVE_AUTO_OPTIONS['native_rate_cash'];m._PREVIEW_BY_KEY['progress_money'].value=2.5
        seen=[];m.make_session_cash=lambda session,selection:seen.append((session,selection)) or 'cash'
        self.assertEqual(m.make_automation_lane('native_rate_cash','session'),'cash');self.assertEqual(seen,[('session',2.5)])
