"""R47 F8 feature row pagination: synthetic UI only, not a native FPS benchmark."""
import unittest
from test_batch import Batch

class FocusRows(unittest.TestCase):
    def setUp(self):
        self.b=Batch();self.b.setUp();self.addCleanup(self.b.doCleanups)
        self.m=self.b.m;self.ui=self.b.gui.imgui
        self.m._category=4
    def render(self,clicks=(),edits=None):
        self.ui.labels=[];self.ui.clicks=set(clicks);self.ui.edits=edits or {}
        self.m.draw();return list(self.ui.labels)
    def sliders(self,labels):
        return {o.identifier for o in self.m.CATEGORIES[4][2] if o.display_name+'##'+o.identifier in labels}
    def test_default_full_then_opt_in_reduces_rows(self):
        baseline=self.render();self.assertFalse(self.m._focus_controls)
        focus=self.render(edits={'Reduced feature rows (6 per page)':True})
        self.assertEqual(len(self.sliders(focus)),6)
        self.assertLess(len(focus),len(baseline));self.assertGreater(len(self.sliders(baseline)),6)
    def test_all_movement_controls_reachable(self):
        all_ids=self.sliders(self.render());self.m._focus_controls=True
        labels=self.render();seen=self.sliders(labels)
        while 'Next controls##focus_next' in labels:
            labels=self.render(['Next controls##focus_next']);seen|=self.sliders(labels)
        self.assertEqual(seen,all_ids);self.assertIn('Previous controls##focus_prev',labels)
    def test_draft_preserved_when_paging(self):
        self.m._focus_controls=True
        label=next(o.display_name+'##'+o.identifier for o in self.m.PREVIEW if o.identifier=='jump')
        self.render(edits={label:2.0});self.render(['Next controls##focus_next'])
        self.assertEqual(self.m.displayed_selection(self.m._PREVIEW_BY_KEY['jump']),2.0);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_disable_focus_restores_full_view(self):
        baseline=self.sliders(self.render());self.m._focus_controls=True;self.render(['Next controls##focus_next'])
        self.assertEqual(self.sliders(self.render(edits={'Reduced feature rows (6 per page)':False})),baseline)
    def test_active_restore_global_even_when_hidden(self):
        self.b.activate('jump',2);self.m._focus_controls=True
        self.render(['Next controls##focus_next']);labels=self.render()
        self.assertIn('Restore All',labels)
        self.render(['Restore All']);self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_category_and_compact_pages_separate(self):
        self.m._focus_controls=True
        self.render(['Next controls##focus_next']);self.assertEqual(self.m._focus_pages[(4,False)],1)
        self.render(edits={'Compact menu (hide preview-only controls)':True});self.assertEqual(self.m._focus_pages[(4,True)],0)
        self.render(edits={'Compact menu (hide preview-only controls)':False});self.assertEqual(self.m._focus_pages[(4,False)],1)
    def test_safety_and_automation_controls_not_paginated(self):
        self.m._focus_controls=True;self.m._category=5
        labels=self.render();self.assertIn('Restore All',labels);self.assertIn('Close menu',labels)
        self.assertIn('Vacuum ammo##vacuum_ammo',labels)
        self.assertIn('I use Offline Local Only; tuning mods disabled##persistent_offline',labels)
    def test_page_navigation_does_not_save_or_write(self):
        self.m._focus_controls=True
        self.m.apply=lambda *_:self.fail('paging must not save')
        self.render(['Next controls##focus_next']);self.render(['Previous controls##focus_prev'])
        self.assertEqual(self.b.f.writes,[]);self.assertEqual(self.b.jump.JumpZVelocity,620.)
