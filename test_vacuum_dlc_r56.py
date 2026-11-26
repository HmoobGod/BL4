"""Synthetic DLC gear scope and reflected body/package identity checks."""
import struct
from test_vacuum_r25 import Obj
from test_vacuum_r26 import Continuous
from test_vacuum_identity_r51 import GearIdentity

class DlcGear(GearIdentity):
    def dlc(self,name='dlc',instance=42,family='ClassMods',pack='Cowbell',beam=8):
        a=self.gear(name,instance)
        family=family+'/HeavyWeapons' if family=='Gadgets' else family
        package=f'/Game/DLC/{pack}/Gear/{family}/Body_Test'
        cls=Obj(self.v.DLC_BODY_TYPE)
        a.BodyData=Obj(package+'.Body_Test',Class=cls,Outer=Obj(package,Class=Obj('/Script/CoreUObject.Package')))
        props=a.Class._properties()
        p=type('ZObjectProperty',(),{'Name':'BodyData','ArrayDim':1,'PropertyClass':cls})()
        a.Class._properties=lambda:props+[p]
        a.AttractEffectComponent.OverrideParameters.ParameterData=struct.pack('<4f',*self.v.PALETTE[beam][1])
        return a
    def relocate(self,*actors):
        self.actors=list(actors);self.assertTrue(self.start(('gear',)));self.tick()
    def test_positive_dlc_gear(self):
        a=self.dlc();self.assertEqual(self.v.classify(a),'gear');self.relocate(a);self.assertEqual([c[0] for c in self.calls],['dlc'])
    def test_families(self):
        for family in self.v.DLC_GEAR_FAMILIES:self.assertEqual(self.v.classify(self.dlc(family=family)),'gear')
    def test_unknown_family(self):self.relocate(self.dlc(family='Unknown'));self.assertFalse(self.calls)
    def test_excluded_pack(self):self.relocate(self.dlc(pack='Mission'));self.assertFalse(self.calls)
    def test_path_mismatch(self):
        a=self.dlc();a.BodyData.Outer.path='/Game/Gear/Other';self.relocate(a);self.assertFalse(self.calls)
    def test_invalid_package_type(self):
        a=self.dlc();a.BodyData.Outer.Class.path='/Script/Engine.Level';self.relocate(a);self.assertFalse(self.calls)
    def test_body_wrapper_type_mismatch(self):
        a=self.dlc();a.BodyData.Class=Obj(self.v.DLC_BODY_TYPE);self.relocate(a);self.assertFalse(self.calls)
    def test_missing_descriptor(self):
        a=self.dlc();props=a.Class._properties()[:-1];a.Class._properties=lambda:props;self.relocate(a);self.assertFalse(self.calls)
    def test_wrong_beam(self):self.relocate(self.dlc(beam=0));self.assertFalse(self.calls)
    def test_high_rarity_filter(self):
        a=self.dlc(beam=4);self.assertEqual(self.v.classify(a),'gear');self.assertIsNone(self.v.classify(a,True))
    def test_dlc_is_not_ammo(self):
        a=self.dlc();self.actors=[a];self.start(('ammo',));self.tick();self.assertFalse(self.calls)
    def test_legacy_dlc_consumables_unchanged(self):
        a=self.drop('ammo','ammo',(400,0,0));a.BodyData.path='/Game/DLC/Cowbell/Pickups/Ammo/Body.Body';self.assertEqual(self.v.classify(a),'ammo');self.actors=[a];self.start(('ammo',));self.tick();self.assertEqual([c[0] for c in self.calls],['ammo'])
    def test_unrecognized_gadget_family_rejected(self):
        self.relocate(self.dlc(family='Gadgets/Unknown'));self.assertFalse(self.calls)
    def test_duplicate_native_id_across_namespaces(self):
        self.relocate(self.dlc(instance=42),self.gear('base',42));self.assertFalse(self.calls)
    def test_final_scope_changes_dlc_package(self):
        a=self.dlc();self.actors=[a];self.start(('gear',));old=self.lease.resolve;calls=0
        def changed():
            nonlocal calls
            calls+=1
            if calls==4:a.BodyData.Outer=Obj(a.BodyData.Outer.path,Class=a.BodyData.Outer.Class)
            return old()
        self.lease.resolve=changed;self.tick();self.assertFalse(self.calls)
    def test_final_scope_changes_beam(self):
        a=self.dlc();self.actors=[a];self.start(('gear',));self.lease.update_preferences(('gear',),30,True);old=self.lease.resolve;calls=0
        def changed():
            nonlocal calls
            calls+=1
            if calls==4:a.AttractEffectComponent.OverrideParameters.ParameterData=struct.pack('<4f',*self.v.PALETTE[4][1])
            return old()
        self.lease.resolve=changed;self.tick();self.assertFalse(self.calls)
    def test_body_replacement_before_dispatch(self):
        a=self.dlc();b=self.dlc('replacement',42);self.actors=[a];old=a.K2_GetActorRotation
        def change():
            a.BodyData=b.BodyData
            return old()
        change.func=old.func;a.K2_GetActorRotation=change;self.start(('gear',));self.tick();self.assertFalse(self.calls)
