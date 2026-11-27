"""Native-shaped energy shield getter/field tests; no game process."""
import unittest
from test_combat_r13 import Node,attr,typ,desc,objdesc
from test_batch import Batch
PATH='/Script/OakGame.OakInventoryStatics:GetShield'
SHIELD='/Script/OakGame.Shield'

class ShieldRates(unittest.TestCase):
    def setUp(self):
        self.b=Batch();self.b.setUp();self.addCleanup(self.b.doCleanups);self.m=self.b.m;self.p=self.b.f.pawn
        self.sh=self.make_shield();self.current=self.sh
        ps=[objdesc('ShieldUser','/Script/Engine.Actor'),objdesc('ReturnValue',SHIELD)]
        cdo=Node();f=Node(Name='GetShield',NumParams=2,Outer=Node(ClassDefaultObject=cdo),_path_name=lambda:PATH,_properties=lambda:ps)
        def get(p):return self.current
        get.func=f;cdo.GetShield=get;self.func=f;self.props=ps
        old=self.b.f.sdk.find_all
        self.b.f.sdk.find_all=lambda *a,**k:list(old(*a,**k))+[f] if a[0]=='Function' else old(*a,**k)
    def make_shield(self):
        r,d=attr(10.),attr(4.)
        cls=typ(SHIELD,desc('RegenRate',r._type),desc('RegenDelay',d._type),objdesc('OwningCharacter','/Script/OakGame.OakCharacter'))
        sh=Node(Name='ShieldInstance',Class=cls,Owner=self.p,OwningCharacter=self.p,RegenRate=r,RegenDelay=d,HasAuthority=lambda:True,IsActorBeingDestroyed=lambda:False,system='Energy')
        self.member(sh,'K2_GetHealthSystem','ZEnumProperty',lambda:Node(name=sh.system),Enum=Node(Name='/Script/OakGame.EShieldHealthSystem'))
        self.member(sh,'GetRegenRate','ZFloatProperty',lambda:r.Value)
        self.member(sh,'GetRegenDelay','ZFloatProperty',lambda:d.Value)
        return sh
    def member(self,sh,name,kind,call,**kwargs):
        p=type(kind,(),dict(Name='ReturnValue',ArrayDim=1,**kwargs))()
        def bound():return call()
        bound.func=Node(NumParams=1,_path_name=lambda:SHIELD+':'+name,_properties=lambda:[p]);setattr(sh,name,bound)
    def activate(self,k,v):self.b.activate('shield_regen_'+k,v)
    def values(self,sh=None):
        sh=sh or self.sh;return (sh.RegenRate.Value,sh.RegenRate.BaseValue,sh.RegenDelay.Value,sh.RegenDelay.BaseValue)
    def test_default_no_write(self):self.assertEqual(self.sh.RegenRate.writes+self.sh.RegenDelay.writes,[]);self.assertIs(self.m.AUTO_OPTIONS['shield_regen_rate'].value,False)
    def test_rate_cycle(self):self.activate('rate',2.);self.assertEqual(self.values(),(20.,20.,4.,4.));self.activate('rate',3.);self.assertEqual(self.values(),(30.,30.,4.,4.));self.activate('rate',1.);self.assertEqual(self.values(),(10.,10.,4.,4.))
    def test_delay_inverse(self):self.activate('delay',2.);self.assertEqual(self.values(),(10.,10.,2.,2.));self.activate('delay',.5);self.assertEqual(self.values(),(10.,10.,8.,8.))
    def test_both_and_jump_restore(self):self.activate('rate',2.);self.activate('delay',2.);self.b.activate('jump',2.);self.assertEqual(self.values(),(20.,20.,2.,2.));self.m.request_stop('test',immediate=True);self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertEqual(self.b.jump.JumpZVelocity,620.)
    def test_armor_refused(self):self.sh.system='Armor';self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_foreign_owner_refused(self):self.sh.OwningCharacter=Node();self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_no_authority(self):self.sh.HasAuthority=lambda:False;self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_signature_refused(self):self.props[1].PropertyClass=Node(Name='/Script/Engine.Actor');self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_getter_mismatch(self):self.member(self.sh,'GetRegenRate','ZFloatProperty',lambda:99.);self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_getter_no_effect_rolls_back(self):self.member(self.sh,'GetRegenRate','ZFloatProperty',lambda:10.);self.activate('rate',2.);self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.m._controller.records)
    def test_join_restore(self):self.activate('rate',2.);self.b.f.players=2;self.m.monitor_tick();self.assertEqual(self.values(),(10.,10.,4.,4.))
    def test_swap_retained_original(self):self.activate('rate',2.);self.current=self.make_shield();self.m.monitor_tick();self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertEqual(self.current.RegenRate.writes,[])
    def test_swap_lost_owner_fault(self):self.activate('rate',2.);self.current=self.make_shield();self.sh.OwningCharacter=None;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.current.RegenRate.writes,[])
    def test_foreign_drift(self):self.activate('rate',2.);self.sh.RegenRate._values['Value']=19.;self.m.monitor_tick();self.assertTrue(self.m._controller.fault);self.assertEqual(self.sh.RegenRate.Value,19.)
    def test_f8_manual_activation(self):self.m._category=6;self.m.auto_consent.value=True;self.b.gui.imgui.edits={'Equipped energy shield recharge rate (experimental)##shield_regen_rate':2.,'Enable Equipped energy shield recharge rate (experimental)##persistent_shield_regen_rate':True};self.m.draw();self.assertEqual(self.sh.RegenRate.writes,[]);self.m.monitor_tick();self.assertEqual(self.values(),(20.,20.,4.,4.))
    def test_zero_baseline(self):self.sh.RegenRate._values.update(Value=0.,BaseValue=0.);self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_mismatched_pair(self):self.sh.RegenRate._values['BaseValue']=9.;self.activate('rate',2.);self.assertEqual(self.sh.RegenRate.writes,[])
    def test_partial_write_rollback(self):self.sh.RegenRate.raise_after='BaseValue';self.activate('rate',2.);self.assertEqual(self.values(),(10.,10.,4.,4.));self.assertFalse(self.m._controller.fault)
