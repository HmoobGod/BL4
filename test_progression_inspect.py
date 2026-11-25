"""Synthetic fixtures only; no game or community asset bytes."""
import io
import math
import struct
import unittest
import zipfile
import progression_inspect as p


def fake_asset(values):
    names=[f'{name}_{i}_'+('A'*32) for i,name in enumerate(p.FIELDS)]+['DoubleProperty','StructProperty','None',p.ASSET,p.ASSET_PATH]
    nm=b''.join(struct.pack('>H',len(n)) for n in names)+''.join(names).encode('ascii')
    header=0x44+26*8+len(nm)
    a=bytearray(header+34)
    struct.pack_into('<I',a,4,header);struct.pack_into('<I',a,52,26)
    a[0x44+26*8:header]=nm
    struct.pack_into('<I',a,header+30,len(p.FIELDS))
    for i in range(len(p.FIELDS)):
        nested=8<=i<20
        d=bytearray(51 if nested else 47)
        struct.pack_into('<4I',d,0,22 if nested else 21,0,i,0)
        struct.pack_into('<I',d,24,16 if nested else 8)
        a+=d
    a+=bytes(12)
    mask=0; payload=bytearray()
    for i,name in enumerate(p.FIELDS):
        if 8<=i<20:payload+=b'\x80\x09\x0f';continue
        v=values.get(name,0.)
        if v==0.:mask|=1<<i
        else:payload+=struct.pack('<d',v)
    return bytes(a)+struct.pack('<HI', (len(p.FIELDS)<<9)|0x180,mask)+payload+struct.pack('<I',0x9E2A83C1)


def fake_toc(parts, version=8):
    n=len(parts);block=65536
    h=bytearray(144);h[:16]=b'-==--==--==--==-';h[80]=8
    struct.pack_into('<10I',h,16,version,144,n,n,12,0,32,block,0,1)
    ids=b''.join(struct.pack('<Q',i+1)+bytes(3)+bytes([1 if i<n-1 else 6]) for i in range(n))
    offsets=b''.join((i*block).to_bytes(5,'big')+len(a).to_bytes(5,'big') for i,a in enumerate(parts))
    table=b'';offset=0
    for a in parts:
        table+=offset.to_bytes(5,'little')+len(a).to_bytes(3,'little')*2+bytes(1);offset+=len(a)
    return bytes(h)+ids+offsets+table,b''.join(parts)


def fake_archive(parts=None, skip=None, invalid_name=None):
    if parts is None:parts=[fake_asset({'Cash':3.,'CombatExperience':7.}),b'container']
    t,d=fake_toc(parts)
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w') as z:
        for suffix,b in [('pak',b'fixture'),('utoc',t),('ucas',d)]:
            if suffix!=skip:z.writestr('Fixture/a.'+suffix,b)
        if invalid_name:z.writestr(invalid_name,b'x')
    f.seek(0);return f


class ProgressionInspection(unittest.TestCase):
    def test_distinct_fields(self):
        data=p.decode_asset(fake_asset({'Cash':3.,'Eridium':2.,'CombatExperience':7.,'LootLuck':13.}))
        self.assertEqual([data[k] for k in ('Cash','Eridium','CombatExperience','LootLuck')],[3.,2.,7.,13.])
    def test_zero_mask(self):
        d=p.decode_asset(fake_asset({}));self.assertEqual(d['CombatExperience'],0.);self.assertEqual(d['LootLuck'],0.)
    def test_negative_source_value(self):self.assertEqual(p.decode_asset(fake_asset({'CombatExperience':-1.}))['CombatExperience'],-1.)
    def test_nonfinite(self):
        with self.assertRaises(ValueError):p.decode_asset(fake_asset({'Cash':math.inf}))
    def test_trailer(self):
        with self.assertRaises(ValueError):p.decode_asset(fake_asset({})+b'x')
    def test_field_order(self):
        a=bytearray(fake_asset({}));h=p.u32(a,4);struct.pack_into('<I',a,h+42,1)
        with self.assertRaises(ValueError):p.decode_asset(a)
    def test_unknown_type(self):
        a=bytearray(fake_asset({}));h=p.u32(a,4);struct.pack_into('<I',a,h+34,99)
        with self.assertRaises(ValueError):p.decode_asset(a)
    def test_container(self):
        self.assertEqual(p.inspect_archive(fake_archive())['Fixture/a']['fields']['Cash'],3.)
    def test_multiple_exports(self):
        r=p.inspect_archive(fake_archive([b'other',fake_asset({'Cash':9.}),b'header']))['Fixture/a'];self.assertEqual(r['package_exports'],2);self.assertEqual(r['fields']['Cash'],9.)
    def test_ambiguous(self):
        with self.assertRaises(ValueError):p.inspect_archive(fake_archive([fake_asset({}),fake_asset({}),b'header']))
    def test_incomplete(self):
        with self.assertRaises(ValueError):p.inspect_archive(fake_archive(skip='pak'))
    def test_traversal(self):
        with self.assertRaises(ValueError):p.inspect_archive(fake_archive(invalid_name='../x.pak'))
    def test_compressed(self):
        t,b=fake_toc([fake_asset({}),b'header']);t=bytearray(t);t[144+22*2+11]=1
        with self.assertRaises(ValueError):list(p.chunks(t,b))
    def test_profile(self):
        r=p.profile(2,4,6);self.assertFalse(r['installable']);self.assertFalse(r['runtime_verified']);self.assertEqual(r['raw_field_intent'],dict(CombatExperience=2,Cash=4,LootLuck=6,Eridium=0.))
    def test_profile_reject(self):
        for v in (True,math.nan,math.inf,-1,10**30):
            with self.subTest(v=v),self.assertRaises(ValueError):p.profile(v,1,1)

if __name__=='__main__':unittest.main()
