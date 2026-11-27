"""Reduced action panels: presentation only, no native FPS claim."""
import unittest
from test_batch import Batch
from types import SimpleNamespace

class ActionPanels(unittest.TestCase):
    def setUp(self):
        self.b=Batch();self.b.setUp();self.addCleanup(self.b.doCleanups)
        self.m=self.b.m;self.ui=self.b.gui.imgui
    def render(self,cat,clicks=(),edits=None):
        self.m._category=cat;self.ui.labels=[];self.ui.clicks=set(clicks);self.ui.edits=edits or {};self.m.draw();return list(self.ui.labels)
    def switch(self,cat,name):
        labels=self.render(cat);button=next(l for l in labels if l.endswith('##action_panel_'+str(cat)+'_'+name))
        return self.render(cat,[button])
    def test_manual_automation_split(self):
        full=self.render(5);self.m._focus_controls=True
        vac=self.render(5);reload=self.switch(5,'Automatic reload')
        self.assertIn('Vacuum ammo##vacuum_ammo',vac);self.assertNotIn('Arm experimental automatic reload (30 sec)',vac)
        self.assertNotIn('Vacuum ammo##vacuum_ammo',reload);self.assertIn('Arm experimental automatic reload (30 sec)',reload)
        self.assertLess(len(vac),len(full));self.assertLess(len(reload),len(full))
    def test_manual_recovery_split(self):
        full=self.render(6);self.m._focus_controls=True
        rec=self.render(6);skill=self.switch(6,'Action skills')
        self.assertIn('Test native timed flesh recovery (2 sec)',rec);self.assertNotIn('Start experimental skill duration assist (30 sec)',rec)
        self.assertIn('Start experimental skill duration assist (30 sec)',skill);self.assertNotIn('Test native timed flesh recovery (2 sec)',skill)
        self.assertLess(len(skill),len(full))
    def test_persistent_lanes_all_reachable(self):
        self.m.auto_master.value=True;self.m._focus_controls=True
        rec=self.render(6);skill=self.switch(6,'Action skills')
        for k in ('health','shield','skill_cooldown','skill_duration'):
            o=self.m.AUTOMATION_OPTIONS[k];label=o.display_name+'##'+o.identifier
            self.assertEqual(label in rec,k in ('health','shield'));self.assertEqual(label in skill,k.startswith('skill_'))
        for o in self.m.SKILL_NATIVE.values(): self.assertIn(o.display_name+'##'+o.identifier,skill)
        self.assertIn('Restore All',skill)
    def test_saved_draft_survives_navigation(self):
        self.m.auto_master.value=True;self.m._focus_controls=True;self.switch(6,'Action skills')
        o=self.m.SKILL_RATES['skill_duration'];self.render(6,edits={o.display_name+'##'+o.identifier:1.7})
        self.switch(6,'Recovery');self.assertEqual(self.m.displayed_selection(o),1.7)
    def test_global_restore_available_hidden(self):
        self.b.activate('jump',2);self.m._focus_controls=True
        labels=self.switch(6,'Action skills');self.assertIn('Restore All',labels)
        self.render(6,['Restore All']);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_global_timer_warning(self):
        self.m._native_overtime_used=True;self.m._focus_controls=True
        for cat in (0,5,6):
            self.assertTrue(any('Native timed flesh test attempted' in l for l in self.render(cat)))
    def test_full_view_restores_all(self):
        self.m._focus_controls=True;self.switch(5,'Automatic reload')
        labels=self.render(5,edits={'Reduced feature rows (6 per page)':False})
        self.assertIn('Vacuum ammo##vacuum_ammo',labels);self.assertIn('Arm experimental automatic reload (30 sec)',labels)
    def test_navigation_independent_and_no_writes(self):
        self.m._focus_controls=True;self.switch(5,'Automatic reload');self.switch(6,'Action skills')
        self.assertEqual(self.m._action_panels,{5:'Automatic reload',6:'Action skills'})
        self.assertEqual(self.b.f.writes,[]);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_stop_visible_when_lane_hidden(self):
        self.m._focus_controls=True;self.m.auto_master.value=True
        self.m._automation_leases['skill_duration']=SimpleNamespace(record=object(),fault=False)
        self.assertIn('Restore All',self.render(6))
