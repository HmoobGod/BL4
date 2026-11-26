"""Synthetic timing of existing slide lease, not native slide physics."""
from test_slide_r45 import SlideScale

class SlideTiming(SlideScale):
    def frame(self, dt):
        self.now += dt
        self.m.monitor_tick()
    def ready(self):
        self.configure(slide_speed=2.)
        self.assertFalse(self.scale.writes)
        return self.m._auto_next
    def test_short_slide_between_reconciliations(self):
        deadline=self.ready();self.begin();self.frame(.06)
        self.assertLess(self.now,deadline);self.assertEqual(self.scale.Value,2.5)
        self.assertEqual(self.m._auto_next,deadline)
        self.end();self.frame(.01);self.assertEqual(self.scale.Value,1.25)
    def test_poll_bound_and_no_repeated_write(self):
        self.ready();self.begin();self.frame(.02);self.assertFalse(self.scale.writes)
        self.frame(.04);self.frame(.01);self.frame(.06)
        self.assertEqual(self.scale.writes,[('Value',2.5)])
    def test_draft_does_not_start(self):
        self.ready();self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY['slide_speed'],1.5)
        self.begin();self.frame(.06);self.assertFalse(self.scale.writes)
    def test_join_before_fast_admission(self):
        self.ready();self.begin();self.p.f.players=2;self.frame(.06);self.assertFalse(self.scale.writes)
    def test_disable_before_fast_admission(self):
        self.ready();self.begin();self.m.apply({'persistent_slide_speed':False});self.frame(.06);self.assertFalse(self.scale.writes)
    def test_other_control_cadence(self):
        self.p.configure(slide_speed=2.,dash_speed=2.,glide_speed=2.);self.tick()
        deadline=self.m._auto_next;self.begin();self.frame(.06)
        self.assertEqual(self.scale.Value,2.5);self.assertEqual(self.m._auto_next,deadline)
        self.assertEqual(self.glide.Value,800.)
        self.frame(.25);self.assertEqual(self.glide.Value,1600.)
    def test_loading_backoff_not_shortened(self):
        self.ready();self.m._auto_next=self.m._slide_next=self.now+1.;self.begin();self.frame(.06);self.assertFalse(self.scale.writes)
    def test_pending_stop_blocks_admission(self):
        self.ready();self.begin();self.m._controller.stop_pending='test stop';self.frame(.06);self.assertFalse(self.scale.writes)
