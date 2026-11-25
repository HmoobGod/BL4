"""R7 elemental opt-in regressions, synthetic SDK only."""
import unittest
import test_r3_persistent

ELEMENTS = {'shock_damage':'ShockModifier','corrosive_damage':'CorrosiveModifier',
            'cryo_damage':'CryoModifier','radiation_damage':'RadiationModifier'}

class ElementalExperiments(unittest.TestCase):
    def setUp(self):
        self.p = test_r3_persistent.Persistent(); self.p.setUp()
        self.addCleanup(self.p.doCleanups)
        self.m, self.f = self.p.m, self.p.f
        self.attrs = {k:getattr(self.f.pawn.ElementalDamageModifiers,n) for k,n in ELEMENTS.items()}
    def values(self,k):
        a=self.attrs[k]; return a.Value,a.BaseValue
    def assert_unmodified(self, exclude=()):
        for k,a in self.attrs.items():
            if k not in exclude: self.assertEqual(a.writes,[],k)
        self.assertEqual(self.f.pawn.DamageCauserData.DamageDealtMultiplier.writes,[])
    def test_all_new_defaults_off_even_saved_preview(self):
        for k in ELEMENTS: self.assertFalse(self.m.AUTO_OPTIONS[k].value)
        self.m.apply({**dict.fromkeys(ELEMENTS,2.),'persistent_master':True,'persistent_offline':True})
        self.p.tick(); self.assert_unmodified()
    def test_shock_individual(self): self.individual('shock_damage')
    def test_corrosive_individual(self): self.individual('corrosive_damage')
    def test_cryo_individual(self): self.individual('cryo_damage')
    def test_radiation_individual(self): self.individual('radiation_damage')
    def individual(self,k):
        self.p.configure(**{k:2.}); self.p.tick(); self.assertEqual(self.values(k),(2.,2.))
        self.m.apply({k:3.}); self.p.tick(); self.assertEqual(self.values(k),(3.,3.))
        self.m.set_auto_setting(self.m.AUTO_OPTIONS[k],False); self.p.tick(); self.assertEqual(self.values(k),(1.,1.))
        self.assert_unmodified((k,)); self.assertEqual(self.p.b.fire.writes,[])
    def test_multi_element_independent_restore(self):
        self.p.configure(shock_damage=2.,cryo_damage=3.); self.p.tick(); self.p.tick()
        self.assertEqual(self.values('shock_damage'),(2.,2.)); self.assertEqual(self.values('cryo_damage'),(3.,3.))
        self.m.set_auto_setting(self.m.AUTO_OPTIONS['shock_damage'],False); self.p.tick()
        self.assertEqual(self.values('shock_damage'),(1.,1.)); self.assertEqual(self.values('cryo_damage'),(3.,3.))
        self.m.set_auto_setting(self.m.auto_master,False); self.p.tick(); self.assertEqual(self.values('cryo_damage'),(1.,1.))
    def test_join_restores_all(self):
        self.p.configure(**dict.fromkeys(ELEMENTS,2.)); [self.p.tick() for _ in ELEMENTS]
        self.f.players=2; self.p.tick()
        for k in ELEMENTS: self.assertEqual(self.values(k),(1.,1.))
        self.assertFalse(self.m._controller.records)
    def test_client_block(self):
        self.f.server=False; self.p.configure(shock_damage=2.); self.p.tick(); self.assert_unmodified()
    def test_no_consent(self):
        self.p.configure(radiation_damage=2.); self.m.apply({'persistent_offline':False}); self.p.tick(); self.assert_unmodified()
    def test_partial_rollback(self):
        self.attrs['cryo_damage'].reject='BaseValue'; self.p.configure(cryo_damage=2.); self.p.tick()
        self.assertEqual(self.values('cryo_damage'),(1.,1.)); self.assertFalse(self.m._controller.fault)
    def test_mismatched_baseline(self):
        self.attrs['corrosive_damage']._values['Value']=1.5; self.p.configure(corrosive_damage=2.); self.p.tick(); self.assert_unmodified()
    def test_general_damage_still_held(self):
        self.assertIn('damage',self.m.DAMAGE_HOLD); self.assertNotIn('damage',self.m.AUTO_OPTIONS)
        self.p.configure(shock_damage=2.); self.m.apply({'damage':4.}); self.p.tick(); self.assert_unmodified(('shock_damage',))
