"""Native-shaped tests of the scoped slide Value-only experiment, not game physics."""
from test_movement_r29 import PersistentMovement
from test_combat_r13 import Node,attr,typ,desc,objdesc

SLIDE='/Game/PlayerCharacters/_Shared/Tricks/ControlledMoves/Move_Slide.Move_Slide'

class SlideScale(PersistentMovement):
    def setUp(self):
        super().setUp()
        self.scale=attr(1.25);self.scale._values['BaseValue']=1.
        self.comp.MaxGroundSpeedScale=self.scale
        self.move=Node(Name=SLIDE,Class=typ('OakControlledMove'),bSpeedAffectedByMaxGroundSpeedScale=True)
        self.rep=Node(_type=typ('ControlledMoveReplicationData',objdesc('ControlledMove','ControlledMove')),ControlledMove=None)
        self.comp.ControlledMoveReplicationData=self.rep
        fields=list(self.comp.Class._properties())+[desc('MaxGroundSpeedScale',self.scale._type),desc('ControlledMoveReplicationData',self.rep._type)]
        self.comp.Class._properties=lambda:fields
        self.active=True
        p=objdesc('ControlledMove','ControlledMove');p.PropertyClass._path_name=lambda:'/Script/GbxGame.ControlledMove'
        self.params=[p,type('ZBoolProperty',(),{'Name':'ReturnValue','ArrayDim':1})()]
        def predicate(move):return self.active and move is self.rep.ControlledMove
        predicate.func=Node(NumParams=2,_path_name=lambda:'/Script/GbxGame.GbxCharacterMovementComponent:IsPerformingSpecificControlledMove',_properties=lambda:self.params)
        self.comp.IsPerformingSpecificControlledMove=predicate
    def begin(self):self.rep.ControlledMove=self.move
    def end(self):self.rep.ControlledMove=None
    def configure(self,**kw):self.p.configure(**kw);self.tick()
    def test_default_off(self):
        self.begin();self.m.apply({'persistent_master':True,'persistent_offline':True,'slide_speed':2.});self.tick();self.assertFalse(self.scale.writes)
    def test_only_active_slide_and_restore(self):
        self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
        self.begin();self.tick();self.assertEqual(self.scale.Value,2.5);self.assertEqual(self.scale.BaseValue,1.)
        self.end();self.tick();self.assertEqual(self.scale.Value,1.25);self.assertFalse(self.m._auto_blocked)
        self.tick();self.assertEqual(self.scale.writes,[('Value',2.5),('Value',1.25)])
        self.begin();self.tick();self.assertEqual(self.scale.Value,2.5)
    def test_native_predicate_false(self):
        self.begin();self.active=False;self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_wrong_move(self):
        self.begin();self.move.Name=SLIDE.replace('Move_Slide','Move_Dash');self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_no_scale_consumer(self):
        self.begin();self.move.bSpeedAffectedByMaxGroundSpeedScale=False;self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_wrong_signature(self):
        self.begin();self.params[0].PropertyClass._path_name=lambda:'/Script/Engine.Actor';self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_live_adjust_and_neutral(self):
        self.begin();self.configure(slide_speed=2.);self.m.apply({'slide_speed':.5});self.tick();self.assertEqual(self.scale.Value,.625)
        self.m.apply({'slide_speed':1.});self.tick();self.assertEqual(self.scale.Value,1.25);self.assertEqual(self.scale.BaseValue,1.)
    def test_feature_disable_keeps_other_controls(self):
        self.begin();self.arm(slide_speed=2.,dash_speed=2.);self.tick();self.m.set_auto_setting(self.m.AUTO_OPTIONS['slide_speed'],False);self.tick();self.assertEqual(self.scale.Value,1.25);self.assertEqual(self.dash.Value,2400.);self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
    def test_join_restores(self):
        self.begin();self.configure(slide_speed=2.);self.p.f.players=2;self.tick();self.assertEqual(self.scale.Value,1.25)
    def test_owner_mismatch(self):
        self.begin();self.comp.OakCharacterOwner=Node();self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_base_drift_never_overwrites(self):
        self.begin();self.configure(slide_speed=2.);self.scale._values['BaseValue']=1.5;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.scale.Value,2.5);self.assertEqual(self.scale.BaseValue,1.5)
    def test_foreign_value_never_overwrites(self):
        self.begin();self.configure(slide_speed=2.);self.scale._values['Value']=3.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.scale.Value,3.)
    def test_predicate_failure_restores(self):
        self.begin();self.configure(slide_speed=2.);old=self.comp.IsPerformingSpecificControlledMove
        def broken(move):raise RuntimeError('native getter unavailable')
        broken.func=old.func;self.comp.IsPerformingSpecificControlledMove=broken;self.tick();self.assertEqual(self.scale.Value,1.25);self.assertFalse(self.m._controller.fault)
    def test_move_changes_inside_predicate(self):
        self.begin();old=self.comp.IsPerformingSpecificControlledMove
        def changing(move):self.end();return True
        changing.func=old.func;self.comp.IsPerformingSpecificControlledMove=changing;self.configure(slide_speed=2.);self.assertFalse(self.scale.writes)
    def test_base_unchanged_after_failed_write(self):
        self.begin();self.scale.raise_after='Value';self.configure(slide_speed=2.);self.assertEqual(self.scale.Value,1.25);self.assertEqual(self.scale.BaseValue,1.)
    def test_stop_during_final_predicate(self):
        self.begin();self.configure(slide_speed=2.);self.end();self.tick();self.scale.writes.clear();self.begin()
        old=self.comp.IsPerformingSpecificControlledMove
        def stopped(move):
            if self.m._controller is not None and self.m._controller.busy and 'slide_speed' in self.m._controller.records:
                self.m._controller.stop_pending='test withdrawal'
            return old(move)
        stopped.func=old.func;self.comp.IsPerformingSpecificControlledMove=stopped;self.tick();self.assertEqual(self.scale.Value,1.25);self.assertFalse(self.scale.writes)
    def test_replacement_scale_not_written(self):
        self.begin();self.configure(slide_speed=2.);other=attr(1.)
        # Same descriptor shape but a different instance identity.
        other._type=self.scale._type;self.comp.MaxGroundSpeedScale=other;self.tick()
        self.assertTrue(self.m._controller.fault);self.assertFalse(other.writes)
    def test_native_exact_baseline_reset_no_reapply(self):
        self.begin();self.configure(slide_speed=2.);self.scale._values['Value']=1.25;self.tick();self.tick()
        self.assertEqual(self.scale.Value,1.25);self.assertTrue(self.m._auto_blocked);self.assertEqual(self.scale.writes,[('Value',2.5)])
