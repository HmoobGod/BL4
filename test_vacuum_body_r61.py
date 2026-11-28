"""Synthetic exact-body and final category checks; not native gameplay."""
import struct
from test_vacuum_r25 import Obj
from test_vacuum_r26 import Continuous

class PickupBody(Continuous):
    def reflected(self,a):
        path=a.BodyData.path; package=path.rpartition('.')[0]
        cls=Obj(self.v.DLC_BODY_TYPE)
        a.BodyData.Class=cls
        a.BodyData.Outer=Obj(package,Class=Obj('/Script/CoreUObject.Package'))
        p=type('ZObjectProperty',(),{'Name':'BodyData','ArrayDim':1,'PropertyClass':cls})()
        a.Class._properties=lambda:[p]
        return a
    def late(self,change):
        self.start(self.v.CATEGORIES);old=self.lease.resolve;calls=0
        def changed():
            nonlocal calls
            calls+=1
            result=old()
            if calls==4:change()
            return result
        self.lease.resolve=changed;self.tick()
        self.assertFalse(self.calls);self.assertFalse(self.lease.attempted)
    def test_reflected_all_categories(self):
        self.actors=[self.reflected(self.drop(k,k,(400,0,0))) for k in self.v.CATEGORIES]
        self.start(self.v.CATEGORIES);self.tick();self.tick()
        self.assertEqual({c[0] for c in self.calls},self.v.CATEGORIES)
    def test_malformed_reflected_body(self):
        self.reflected(self.a);self.a.BodyData.Class=Obj(self.v.DLC_BODY_TYPE)
        self.start();self.tick();self.assertFalse(self.calls)
    def test_malformed_package(self):
        self.reflected(self.a);self.a.BodyData.Outer.path='/Game/Wrong'
        self.start();self.tick();self.assertFalse(self.calls)
    def test_ambiguous_descriptor(self):
        self.reflected(self.a);props=self.a.Class._properties();self.a.Class._properties=lambda:props*2
        self.start();self.tick();self.assertFalse(self.calls)
    def test_late_body_same_path_replacement(self):
        self.late(lambda:setattr(self.a,'BodyData',Obj(self.a.BodyData.path)))
    def test_late_category_switch(self):
        replacement=self.drop('cash','cash',(300,0,0))
        def switch():
            self.a.BodyData=replacement.BodyData
            self.a.AttractEffectComponent=replacement.AttractEffectComponent
        self.late(switch)
    def test_late_beam_change(self):
        self.late(lambda:setattr(self.a.AttractEffectComponent.OverrideParameters,'ParameterData',struct.pack('<4f',*self.v.PALETTE[1][1])))
    def test_late_lock(self):
        self.late(lambda:setattr(self.a.UsableActorState,'bInteractabilityLockedReplicated',True))
    def test_late_owner(self):self.late(lambda:setattr(self.a,'Owner',Obj('foreign')))
    def test_late_destroy(self):self.late(lambda:setattr(self.a,'IsActorBeingDestroyed',lambda:True))
    def test_late_hidden(self):self.late(lambda:setattr(self.a,'bHidden',True))
    def test_late_level_change(self):self.late(lambda:setattr(self.a,'Outer',Obj('other',Class=Obj('/Script/Engine.Level'))))
    def test_late_root_change(self):self.late(lambda:setattr(self.a.RootPrimitiveComponent,'Outer',Obj('other')))
    def test_late_package_identity(self):
        self.reflected(self.a)
        self.late(lambda:setattr(self.a.BodyData,'Outer',Obj(self.a.BodyData.Outer.path,Class=self.a.BodyData.Outer.Class)))
    def test_base_gear_late_beam(self):
        a=self.drop('gear','gear',(400,0,0));self.a=a;self.actors=[a]
        self.late(lambda:setattr(a.AttractEffectComponent.OverrideParameters,'ParameterData',struct.pack('<4f',*self.v.PALETTE[0][1])))
    def test_late_stop_in_active_check(self):
        def stop():
            self.lease.stop('during active');return False
        self.late(lambda:setattr(self.a,'IsActorBeingDestroyed',stop))

    def exact_currency(self,kind='eridium',reflected=True):
        a=self.drop(kind,kind,(400,0,0))
        a.BodyData.path=(self.v.ERIDIUM_SINGLE_STACK_BODY if kind=='eridium' else self.v.CASH_SINGLE_STACK_BODY)
        if reflected:self.reflected(a)
        return a
    def test_exact_eridium_single_stack_relocated(self):
        a=self.exact_currency();self.actors=[a]
        self.assertEqual(self.v.classify(a),'eridium')
        self.start(('eridium',));self.tick()
        self.assertEqual(self.calls,[('eridium',(0,0,-40),'rotation')])
    def test_exact_currency_filters_independent(self):
        self.actors=[self.exact_currency(),self.exact_currency('cash')]
        self.start(('cash',));self.tick();self.assertEqual([c[0] for c in self.calls],['cash'])
        self.lease.update_preferences(('eridium',),30,False);self.tick()
        self.assertEqual([c[0] for c in self.calls],['cash','eridium'])
    def test_exact_eridium_requires_reflected_body(self):
        self.actors=[self.exact_currency(reflected=False)]
        self.start(('eridium',));self.tick();self.assertFalse(self.calls)
    def test_exact_eridium_requires_matching_package(self):
        a=self.exact_currency();a.BodyData.Outer.path='/Game/World/Other';self.actors=[a]
        self.start(('eridium',));self.tick();self.assertFalse(self.calls)
    def test_exact_eridium_requires_matching_beam(self):
        a=self.exact_currency();a.AttractEffectComponent.OverrideParameters.ParameterData=struct.pack('<4f',*self.v.PALETTE[1][1]);self.actors=[a]
        self.start(('eridium','cash'));self.tick();self.assertFalse(self.calls)
    def test_unknown_eridium_pile_not_admitted(self):
        a=self.exact_currency();a.BodyData.path=a.BodyData.path.replace('Single','Other');a.BodyData.Outer.path=a.BodyData.path.rpartition('.')[0];self.actors=[a]
        self.start(('eridium',));self.tick();self.assertFalse(self.calls)
    def test_exact_eridium_late_body_replacement(self):
        self.a=self.exact_currency();self.actors=[self.a]
        self.late(lambda:setattr(self.a,'BodyData',self.exact_currency().BodyData))
    def test_exact_eridium_late_vendor_lock(self):
        self.a=self.exact_currency();self.actors=[self.a]
        self.late(lambda:setattr(self.a.UsableActorState,'bInteractabilityLockedReplicated',True))
    def test_existing_exact_cash_without_reflection_retained(self):
        self.actors=[self.exact_currency('cash',reflected=False)]
        self.start(('cash',));self.tick();self.assertEqual([c[0] for c in self.calls],['cash'])
