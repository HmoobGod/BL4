"""Native-shaped equipped grenade cooldown tests (no game)."""
import unittest
from test_batch import Batch
from test_combat_r13 import Node, attr, typ, desc, objdesc
GADGET='/Script/OakGame.GrenadeGadget'
GETTER='/Script/OakGame.OakCharacter:GetGrenadeGadget'
class GadgetCooldown(unittest.TestCase):
    def setUp(self):
        self.b=Batch();self.b.setUp();self.addCleanup(self.b.doCleanups);self.m=self.b.m;self.p=self.b.f.pawn
        self.g=self.make();self.current=self.g
        self.props=[objdesc('ReturnValue',GADGET)]
        def getter():return self.current
        getter.func=Node(NumParams=1,_path_name=lambda:GETTER,_properties=lambda:self.props)
        self.p.GetGrenadeGadget=getter
    def make(self):
        a=attr(12.)
        flag=type('ZBoolProperty',(),{'Name':'bIsUsing','ArrayDim':1})()
        return Node(Name='GrenadeInstance',Class=typ(GADGET,desc('CooldownTime',a._type),objdesc('OwningCharacter','/Script/OakGame.OakCharacter'),flag),CooldownTime=a,Owner=self.p,OwningCharacter=self.p,bIsUsing=False,HasAuthority=lambda:True,IsActorBeingDestroyed=lambda:False,NumberOfCharges=1)
    def activate(self,v):self.b.activate('grenade_cooldown',v)
    def vals(self):return self.g.CooldownTime.Value,self.g.CooldownTime.BaseValue
    def test_manual_only_and_default(self):self.assertFalse(self.m.AUTO_OPTIONS['grenade_cooldown'].value);self.assertEqual(self.g.CooldownTime.writes,[])
    def test_cycle(self):
        self.activate(2.);self.assertEqual(self.vals(),(6.,6.));self.activate(.5);self.assertEqual(self.vals(),(24.,24.));self.activate(1.);self.assertEqual(self.vals(),(12.,12.));self.assertEqual(self.g.NumberOfCharges,1)
    def test_busy_refused(self):self.g.bIsUsing=True;self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_foreign_owner_refused(self):self.g.OwningCharacter=Node();self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_signature_refused(self):self.props[0].PropertyClass=Node(Name='/Script/Engine.Actor');self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_zero_refused(self):self.g.CooldownTime._values.update(Value=0.,BaseValue=0.);self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_mismatched_pair(self):self.g.CooldownTime._values['Value']=11.;self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
    def test_using_retains_setting(self):self.activate(2.);self.g.bIsUsing=True;self.m.monitor_tick();self.assertEqual(self.vals(),(6.,6.));self.assertIn('grenade_cooldown',self.m._controller.records)
    def test_swap_restores_original(self):self.activate(2.);self.current=self.make();self.m.monitor_tick();self.assertEqual(self.vals(),(12.,12.));self.assertFalse(self.current.CooldownTime.writes)
    def test_lost_original_fault(self):self.activate(2.);self.current=self.make();self.g.OwningCharacter=None;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertFalse(self.current.CooldownTime.writes)
    def test_join_restores(self):self.activate(2.);self.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.vals(),(12.,12.))
    def test_foreign_drift(self):self.activate(2.);self.g.CooldownTime._values['Value']=7.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.vals(),(7.,6.))
    def test_partial_write_rollback(self):self.g.CooldownTime.raise_after='BaseValue';self.activate(2.);self.assertEqual(self.vals(),(12.,12.));self.assertFalse(self.m._controller.fault)
    def test_f8_queued(self):
        self.m._category=6;self.m.auto_consent.value=True;self.b.gui.imgui.edits={'Grenade gadget cooldown speed (experimental)##grenade_cooldown':3.,'Enable Grenade gadget cooldown speed (experimental)##persistent_grenade_cooldown':True};self.m.draw();self.assertFalse(self.g.CooldownTime.writes);self.m.monitor_tick();self.assertEqual(self.vals(),(4.,4.))
    def test_getter_changes_owner(self):
        old=self.p.GetGrenadeGadget;calls=[]
        def changed():
            calls.append(1)
            if len(calls)==2:self.g.OwningCharacter=Node()
            return old()
        changed.func=old.func;self.p.GetGrenadeGadget=changed
        self.activate(2.);self.assertFalse(self.g.CooldownTime.writes)
