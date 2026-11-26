import unittest
from types import SimpleNamespace as N
from native_recovery_binding import SIGNATURES, DAMAGE, SKILL, bind_exact, recovery_bindings

def fake(path):
    specs=SIGNATURES[path]; props=[]
    for s in specs:
        p=type(s.kind,(),{})(); p.Name=s.name; p.ArrayDim=1
        if s.target:
            t=N(_path_name=lambda target=s.target:target)
            setattr(p,'Struct' if s.kind=='ZStructProperty' else 'PropertyClass',t)
        props.append(p)
    f=N(_path_name=lambda:path, NumParams=len(props), _properties=lambda:props)
    cdo=N(); f.Outer=N(_path_name=lambda:path.rsplit(':',1)[0],ClassDefaultObject=cdo)
    def bound(*args): raise AssertionError('binding must never invoke native code')
    bound.func=f; setattr(cdo,path.rsplit(':',1)[1],bound)
    return f,props,bound

class Binding(unittest.TestCase):
    def test_bind_all_health(self):
        triples=[fake(DAMAGE+n) for n in ('StartHealthRegen','StopHealthRegen','GetHealthPoolPercent')]
        self.assertEqual(recovery_bindings(t[0] for t in triples),tuple(t[2] for t in triples))
    def test_missing_stop(self):
        with self.assertRaises(ValueError): recovery_bindings([fake(DAMAGE+'StartHealthRegen')[0]])
    def test_duplicate(self):
        path=DAMAGE+'StartHealthRegen'; f,*_=fake(path)
        with self.assertRaises(ValueError): bind_exact([f,f],path)
    def test_bad_rate_type(self):
        path=DAMAGE+'StartHealthRegen'; f,p,_=fake(path); p[2].Struct._path_name=lambda:'/Script/Wrong.GbxAttributeInit'
        with self.assertRaises(ValueError): bind_exact([f],path)
    def test_bad_tags(self):
        path=DAMAGE+'StartHealthRegen'; f,p,_=fake(path); p[5].ArrayDim=2
        with self.assertRaises(ValueError): bind_exact([f],path)
    def test_bad_owner(self):
        path=DAMAGE+'StopHealthRegen'; f,p,_=fake(path); f.Outer._path_name=lambda:'/Script/Wrong.DamageStatics'
        with self.assertRaises(ValueError): bind_exact([f],path)
    def test_bad_count(self):
        path=DAMAGE+'StopHealthRegen'; f,p,_=fake(path); f.NumParams=3
        with self.assertRaises(ValueError): bind_exact([f],path)
    def test_bad_bound(self):
        path=DAMAGE+'StopHealthRegen'; f,p,b=fake(path); b.func=N(_path_name=lambda:'other')
        with self.assertRaises(ValueError): bind_exact([f],path)
    def test_readonly_skill_paths(self):
        for path in SIGNATURES:
            if path.startswith(SKILL):
                f,p,b=fake(path); self.assertIs(bind_exact([f],path),b)
        with self.assertRaises(KeyError): bind_exact([],SKILL+'RefillCooldown')
