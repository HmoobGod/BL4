import hashlib
import pathlib
import struct
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace
from decode_ncs import frame, decode, extract_pinned_zip, BLOCK

def outer(flag, raw, payload):
    return b'\x01NCS'+struct.pack('<III',flag,raw,len(payload))+payload

def inner(flags,count,table,body):
    return b'\xb7\x75\x63\x62'+b'\0'*4+struct.pack('>II',flags,count)+b'\0'*48+table+body

class Tests(unittest.TestCase):
    def test_raw(self): self.assertEqual(decode(outer(0,4,b'ABCD'), 'unused'),b'ABCD')
    def test_raw_size(self):
        with self.assertRaises(ValueError): frame(outer(0,5,b'ABCD'))
    def test_compressed_single(self): self.assertEqual(frame(outer(3,8,inner(0,1,b'',b'123'))),[(b'123',8,True)])
    def test_multi(self): self.assertEqual(frame(outer(3,BLOCK+3,inner(0x03030812,2,struct.pack('>II',2,3),b'12345'))),[(b'12',BLOCK,True),(b'345',3,True)])
    def test_explicit_raw_multi(self):
        data=outer(3,4,inner(0x03030812,1,struct.pack('>I',4),b'ABCD'))
        self.assertEqual(frame(data),[(b'ABCD',4,True)])
        self.assertEqual(decode(data,'unused',(0,)),b'ABCD')
    def test_mixed_raw_multi(self):
        data=outer(3,BLOCK+3,inner(0x03030812,2,struct.pack('>II',2,3),b'12345'))
        self.assertEqual(frame(data,(1,)),[(b'12',BLOCK,True),(b'345',3,False)])
    def test_raw_wrong_length(self):
        with self.assertRaises(ValueError):frame(outer(3,8,inner(0x03030812,1,struct.pack('>I',1),b'1')),(0,))
    def test_raw_index_range_and_duplicate(self):
        data=outer(3,4,inner(0x03030812,1,struct.pack('>I',4),b'ABCD'))
        for ids in ((1,),(0,0),(-1,),(True,)):
            with self.subTest(ids=ids),self.assertRaises(ValueError):frame(data,ids)
    def test_raw_index_single_refused(self):
        with self.assertRaises(ValueError):frame(outer(3,8,inner(0,1,b'',b'123')),(0,))
    def test_count(self):
        with self.assertRaises(ValueError): frame(outer(3,8,inner(0x03030812,2,struct.pack('>II',1,1),b'12')))
    def test_extra(self):
        with self.assertRaises(ValueError): frame(outer(3,8,inner(0x03030812,1,struct.pack('>I',1),b'12')))
    def test_truncated(self):
        with self.assertRaises(ValueError): frame(outer(3,8,inner(0x03030812,1,struct.pack('>I',3),b'12')))
    def test_late_length(self):
        with patch('decode_ncs.subprocess.run',return_value=SimpleNamespace(stdout=b'wrong')):
            with self.assertRaises(ValueError): decode(outer(3,8,inner(0,1,b'',b'123')),'decoder')
    def test_decoder_input(self):
        with patch('decode_ncs.subprocess.run',return_value=SimpleNamespace(stdout=b'abcdefgh')) as run:
            self.assertEqual(decode(outer(3,8,inner(0,1,b'',b'123')),'decoder'),b'abcdefgh')
            self.assertEqual(run.call_args.kwargs['input'],b'123')
            self.assertEqual(run.call_args.args[0][1:],['decompress','8'])
    def test_pinned_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'test.zip'; data=outer(0,4,b'ABCD')
            with zipfile.ZipFile(p,'w') as z: z.writestr('test.pak',b'prefix'+data+b'tail')
            self.assertEqual(extract_pinned_zip(p,hashlib.sha256(p.read_bytes()).hexdigest()),data)
            with self.assertRaises(ValueError): extract_pinned_zip(p,'0'*64)
    def test_ambiguous(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'test.zip'; data=outer(0,4,b'ABCD')
            with zipfile.ZipFile(p,'w') as z: z.writestr('test.pak',data+data)
            with self.assertRaises(ValueError): extract_pinned_zip(p,hashlib.sha256(p.read_bytes()).hexdigest())
if __name__=='__main__': unittest.main()
