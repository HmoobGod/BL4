import unittest
from types import SimpleNamespace as N
from ammo_identity import identify, inspect_candidate, body_is_ammo, material_family


BODY = '/Game/Pickups/Ammo/Example'
MATERIAL = 'MI_AMMO_SMG'


class Obj(N):
    def _get_address(self):
        return self.token


def actor():
    mat = Obj(token=5, Name=MATERIAL)
    root = Obj(token=4, GetNumMaterials=lambda: 1, GetMaterial=lambda i: mat)
    return Obj(token=1, Class=N(Name='InventoryPickup'), bActorIsBeingDestroyed=False,
               BodyData=Obj(token=2, Outer=Obj(token=3, Name=BODY)), RootPrimitiveComponent=root)


class AmmoIdentityTests(unittest.TestCase):
    def test_agreement(self):
        self.assertEqual(identify('InventoryPickup', BODY, MATERIAL, 1).family, 'smg')

    def test_supported_families(self):
        for token, family in [('Sniper','sniper'), ('Shotguns','shotgun'), ('Assault','assault_rifle'), ('Pistol','pistol')]:
            self.assertEqual(material_family('MI_AMMO_'+token), family)

    def test_wrong_body(self):
        for path in ['', '/Game/Gear/Ammo/X', '/Game/Pickups/Money/X', '/Game/DLC/X/Pickups/Ammo/X', '/Game/Pickups/Ammo', '/Game/Pickups/Ammo/../Gear', '/Game/Pickups/Ammo/', None]:
            self.assertFalse(body_is_ammo(path))
            self.assertIsNone(identify('InventoryPickup', path, MATERIAL, 1))

    def test_wrong_material(self):
        for name in ['MI_AMMO', 'MI_AMMO_UNKNOWN', 'MI_AMMO_ORDNANCE', 'MI_MONEY_SMG', 'MID_AMMO_SMG', 'XMI_AMMO_SMG', 'MI_AMMO_SMG!', None]:
            self.assertIsNone(identify('InventoryPickup', BODY, name, 1))

    def test_wrong_class_or_identity(self):
        for token in [None, 0, -1, True, 1.0]:
            self.assertIsNone(identify('InventoryPickup', BODY, MATERIAL, token))
        self.assertIsNone(identify('InventoryBase', BODY, MATERIAL, 1))

    def test_read_adapter(self):
        self.assertEqual(inspect_candidate(actor(), still_current=lambda:True, excluded_identities=frozenset()).family, 'smg')

    def test_vendor(self):
        a=actor()
        a.RootPrimitiveComponent.GetNumMaterials=lambda: self.fail('unexpected getter')
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset({1})))

    def test_unverified_context(self):
        for current in [False, 1, None]:
            self.assertIsNone(inspect_candidate(actor(), still_current=lambda:current, excluded_identities=frozenset()))
        self.assertIsNone(inspect_candidate(actor(), still_current=lambda:True, excluded_identities=set()))

    def test_destroyed(self):
        a=actor(); a.bActorIsBeingDestroyed=True
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))

    def test_unknown_body_skips_materials(self):
        a=actor(); a.BodyData.Outer.Name='/Game/Pickups/Health/X'
        calls=[]; a.RootPrimitiveComponent.GetNumMaterials=lambda: calls.append(1)
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))
        self.assertEqual(calls, [])

    def test_invalid_material_counts(self):
        for count in [0, -1, 33, True, 1.0]:
            a=actor(); a.RootPrimitiveComponent.GetNumMaterials=lambda:count
            self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))

    def test_context_lost_before_getters(self):
        a=actor(); checks=iter([True,False]); calls=[]
        a.RootPrimitiveComponent.GetNumMaterials=lambda: calls.append(1)
        self.assertIsNone(inspect_candidate(a, still_current=lambda:next(checks), excluded_identities=frozenset()))
        self.assertEqual(calls, [])

    def test_body_replacement(self):
        a=actor(); old=a.RootPrimitiveComponent.GetMaterial
        def changed(i):
            a.BodyData=Obj(token=7, Outer=Obj(token=3, Name=BODY)); return old(i)
        a.RootPrimitiveComponent.GetMaterial=changed
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))

    def test_material_replacement(self):
        a=actor(); mats=iter([Obj(token=5,Name=MATERIAL),Obj(token=6,Name=MATERIAL)])
        a.RootPrimitiveComponent.GetMaterial=lambda i: next(mats)
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))

    def test_missing_property(self):
        a=actor(); del a.BodyData
        self.assertIsNone(inspect_candidate(a, still_current=lambda:True, excluded_identities=frozenset()))


if __name__=='__main__':
    unittest.main()
