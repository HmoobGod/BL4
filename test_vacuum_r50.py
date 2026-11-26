"""Synthetic beam-only selective gear relocation; no native rarity claim."""
import struct
from test_vacuum_r25 import VacuumTests
from test_vacuum_r26 import Continuous

class HighGear(Continuous):
    def beam(self,a,index):
        a.AttractEffectComponent.OverrideParameters.ParameterData=struct.pack('<4f',*self.v.PALETTE[index][1]);return a
    def gear(self,name,index):return self.beam(self.drop(name,'gear',(400,0,0)),index)
    def test_both_high_colors(self):
        self.actors=[self.gear('legend',8),self.gear('pearl',13),self.gear('common',4),self.gear('epic',12)]
        self.start(('gear',));self.lease.update_preferences(('gear',),30,True);self.tick();self.assertEqual({c[0] for c in self.calls},{'legend','pearl'})
    def test_all_lower_palettes_rejected(self):
        for index in (4,5,6,7,9,10,11,12):
            a=self.gear('gear',index);self.assertEqual(self.v.classify(a),'gear');self.assertIsNone(self.v.classify(a,True))
    def test_default_unchanged(self):
        self.actors=[self.gear('common',4),self.gear('epic',12)];self.start(('gear',));self.tick();self.assertEqual(len(self.calls),2)
    def test_consumables_independent(self):
        self.actors += [self.gear('common',4),self.gear('legend',8)];self.start(('ammo','gear'));self.lease.update_preferences(('ammo','gear'),30,True);self.tick();self.assertEqual({c[0] for c in self.calls},{'a','legend'})
    def test_high_color_wrong_body(self):
        self.beam(self.a,8);self.assertIsNone(self.v.classify(self.a,True))
    def test_late_downgrade(self):
        a=self.gear('legend',8);self.actors=[a];self.start(('gear',));self.lease.update_preferences(('gear',),30,True);old=a.K2_GetActorRotation
        def downgrade():self.beam(a,4);return old()
        downgrade.func=old.func;a.K2_GetActorRotation=downgrade;self.tick();self.assertFalse(self.calls)
    def test_live_filter_disable_keeps_ledger(self):
        self.actors=[self.gear('legend',8),self.gear('common',4)];self.start(('gear',));record=self.lease.record;self.lease.update_preferences(('gear',),30,True);self.tick();self.lease.update_preferences(('gear',),30,False);self.tick();self.assertEqual([c[0] for c in self.calls],['legend','common']);self.assertIs(self.lease.record,record)
    def test_invalid_filter_atomic(self):
        self.start();self.assertRaises(ValueError,self.lease.update_preferences,('gear',),5,'yes');self.assertEqual(self.lease.categories,{'ammo'});self.assertFalse(self.lease.high_gear_only)
    def test_preference_draft_and_reset(self):
        m=self.base.m;self.assertFalse(m.VACUUM_HIGH_PREF.value);m._vacuum_high_gear=True;self.assertFalse(m.VACUUM_HIGH_PREF.value);m.save_vacuum_preferences();self.assertTrue(m.VACUUM_HIGH_PREF.value);m._vacuum_high_gear=False;m.load_vacuum_preferences();self.assertTrue(m._vacuum_high_gear);m.reset();self.assertFalse(m._vacuum_high_gear);self.assertFalse(m.VACUUM_HIGH_PREF.value)
    def test_manual_arm_ui(self):
        m=self.base.m;self.base.open();m._category=5;m._vacuum_filters['gear']=True;queued=[];m.activate_feature=lambda *args:queued.append(args);self.base.gui.imgui.edits={'Gear: legendary/pearlescent beams only##vacuum_high_gear':True};self.base.gui.imgui.clicks={'Arm experimental Loot Vacuum (30 sec)'};m.draw();self.assertEqual(queued,[('loot_vacuum',(('gear',),30.,True))]);self.assertFalse(m.VACUUM_HIGH_PREF.value)
