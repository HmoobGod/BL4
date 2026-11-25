import sys, types, unittest
from test_foundation import Test as Base

class ValueProbe(unittest.TestCase):
    def setUp(self):
        self.base=Base(); self.base.setUp(); self.m=self.base.m
        self.calls=[]; self.pawn=types.SimpleNamespace(Class=types.SimpleNamespace(Name='OakCharacter'))
        self.pc=types.SimpleNamespace(Pawn=self.pawn, IsLocalPlayerController=lambda:True, HasAuthority=lambda:True)
        sys.modules['mods_base'].get_pc=lambda **kw:self.pc
        self.values=[1.0,1.0,0.0]
        def get(name, pawn, default):
            self.calls.append((name,pawn,default)); return self.values[len(self.calls)-1]
        get.func=types.SimpleNamespace(_path_name=lambda:self.m.GETTER_PATH)
        self.props=[type(t,(),{'Name':n})() for n,t in self.m.GETTER_SIGNATURE]
        self.fn=types.SimpleNamespace(Name='GetValueOfAttribute',NumParams=4,_path_name=lambda:self.m.GETTER_PATH,
            _properties=lambda:self.props,Outer=types.SimpleNamespace(ClassDefaultObject=types.SimpleNamespace(GetValueOfAttribute=get)))
        self.sdk=types.SimpleNamespace(find_all=lambda *a,**kw:[self.fn])
    def tearDown(self): self.base.tearDown()
    def test_valid(self):
        r,n=self.m.read_reward_attributes(self.sdk); self.assertEqual(n,3); self.assertEqual(len(self.calls),3); self.assertTrue(all(c[1] is self.pawn for c in self.calls)); self.assertIn('observed value 0.0',r)
    def test_sentinel(self):
        self.values=[-123456.0,1.0,0.0]; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],2)
    def test_invalid(self):
        self.values=[float('nan'),False,('x',)]; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0)
    def test_signature(self):
        self.fn.NumParams=5; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)
    def test_duplicates(self):
        self.sdk.find_all=lambda *a,**kw:[self.fn,self.fn]; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)
    def test_nonlocal(self):
        self.pc.IsLocalPlayerController=lambda:False; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)
    def test_no_authority(self):
        self.pc.HasAuthority=lambda:False; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)
    def test_no_pawn(self):
        self.pc.Pawn=None; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)
    def test_wrong_binding(self):
        self.fn.Outer.ClassDefaultObject.GetValueOfAttribute.func._path_name=lambda:'other'; self.assertEqual(self.m.read_reward_attributes(self.sdk)[1],0); self.assertFalse(self.calls)

if __name__=='__main__': unittest.main(defaultTest='ValueProbe',verbosity=2)
