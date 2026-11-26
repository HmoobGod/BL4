"""Native-shaped local movement controls; no gameplay execution."""
from test_movement_r29 import PersistentMovement
from test_combat_r13 import attr,desc,Node

class GlideHandling(PersistentMovement):
    keys={'glide_air_control':'GlidingAirControl','glide_boost':'GlidingSpeedBoost','glide_acceleration':'GlidingAcceleration','glide_deceleration':'GlidingDeceleration','grapple_cost':'VaultPowerCost_Grapple','slam_cost':'VaultPowerCost_GroundSlam'}
    def setUp(self):
        super().setUp()
        self.extra={k:attr(10.) for k in self.keys}
        fields=list(self.comp.Class._properties())
        for k,n in self.keys.items():
            a=self.extra[k];setattr(self.comp,n,a);fields.append(desc(n,a._type))
        self.comp.Class._properties=lambda:fields
    def values(self):return tuple((a.Value,a.BaseValue) for a in self.extra.values())
    def test_new_defaults_off(self):
        self.m.apply({'persistent_master':True,'persistent_offline':True,**dict.fromkeys(self.keys,2.)});self.tick();self.assertEqual(self.values(),((10.,10.),)*6)
    def test_all_with_automation(self):
        self.arm(**dict.fromkeys(self.keys,.5));[self.tick() for _ in range(3)];self.assertEqual(self.values(),((5.,5.),)*6);self.assertEqual(set(self.m._automation_leases),{'vacuum','reload'})
        self.m.set_auto_setting(self.m.auto_master,False);self.tick();self.assertEqual(self.values(),((10.,10.),)*6)
    def test_independent_update(self):
        self.arm(glide_boost=2.,glide_acceleration=.5);self.tick();self.m.apply({'glide_boost':1.,'glide_acceleration':3.});self.tick();self.assertEqual(self.extra['glide_boost'].Value,10.);self.assertEqual(self.extra['glide_acceleration'].Value,30.)
    def test_cost_positive_floor(self):
        self.arm(grapple_cost=.1,slam_cost=.1);self.tick();self.assertEqual(self.extra['grapple_cost'].Value,1.);self.assertEqual(self.extra['slam_cost'].Value,1.)
    def test_owner_refused(self):
        self.comp.OakCharacterOwner=Node();self.p.configure(glide_boost=2.);self.tick();self.assertFalse(self.extra['glide_boost'].writes)
    def test_zero_refused(self):
        self.extra['glide_acceleration']._values.update(Value=0.,BaseValue=0.);self.p.configure(glide_acceleration=2.);self.tick();self.assertFalse(self.extra['glide_acceleration'].writes)
    def test_join_restores(self):
        self.arm(**dict.fromkeys(self.keys,2.));[self.tick() for _ in range(3)];self.assertEqual(self.values(),((20.,20.),)*6);self.p.f.players=2;self.tick();self.assertEqual(self.values(),((10.,10.),)*6);self.assertFalse(self.m._automation_leases)
    def test_foreign_drift(self):
        self.arm(glide_boost=2.);self.extra['glide_boost']._values['Value']=19.;self.tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.extra['glide_boost'].Value,19.)
    def test_draft_selection(self):
        self.arm(glide_boost=2.);self.m.queue_auto_edit(self.m._PREVIEW_BY_KEY['glide_boost'],3.);self.assertEqual(self.m.auto_desired()['glide_boost'],2.);self.m.flush_auto_edits(force=True);self.tick();self.assertEqual(self.extra['glide_boost'].Value,30.)
