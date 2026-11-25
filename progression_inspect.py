"""Read-only inspection of the observed BL4 difficulty struct layout.
No extraction to disk, modification, repacking, SDK calls, or game access.
Not a general-purpose IoStore/Zen parser. Reject unknown layouts.
Format references: UAssetAPI FFragment/FUnversionedHeader; retoc IoStore.
"""
import argparse
import hashlib
import json
import math
import re
import struct
import zipfile
from pathlib import PurePosixPath

ASSET = 'Struct_Player_Difficulty_Balance'
ASSET_PATH = '/Game/GameData/Balance/' + ASSET
FIELDS = ('DamageTaken','DamageDealt','LootLuck','AITimeToBestAccuracy',
          'AIDmgPercentToWorstAccuracy','Cash','Eridium','CombatExperience',
          'ElementalDamageTaken','CorrosiveDamageTaken','CryoDamageTaken',
          'FireDamageTaken','ShockDamageTaken','RadiationDamageTaken',
          'ElementalDamageDealt','CorrosiveDamageDealt','CryoDamageDealt',
          'FireDamageDealt','ShockDamageDealt','RadiationDamageDealt','EnemyHealth')
LIMIT = 1024 * 1024

def require(condition, message):
    if not condition:
        raise ValueError(message)

def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]

def chunks(toc, data):
    require(len(toc) >= 144 and toc[:16] == b'-==--==--==--==-', 'not supported IoStore')
    v, header, n, blocks, stride, methods, _, blocksize, directory, partitions = struct.unpack_from('<10I', toc,16)
    require(v in (5,8) and header == 144 and 0 < n <= 64 and blocks == n and stride == 12 and methods == 0 and partitions == 1 and toc[80] == 8 and not any(toc[96:144]), 'unsupported TOC layout')
    table = header + 22*n
    require(table + 12*n + directory <= len(toc), 'truncated TOC')
    end = 0
    for i in range(n):
        o = table + 12*i
        start = int.from_bytes(toc[o:o+5], 'little')
        size = int.from_bytes(toc[o+5:o+8], 'little')
        unpacked = int.from_bytes(toc[o+8:o+11], 'little')
        p = header+12*n+10*i
        logical = int.from_bytes(toc[p:p+5], 'big')
        length = int.from_bytes(toc[p+5:p+10], 'big')
        require(toc[o+11] == 0 and size == unpacked == length and logical == i*blocksize and 0 < size <= blocksize and start == end and start+size <= len(data), 'unsupported chunk mapping')
        end = start+size
        if toc[header+12*i+11] == 1:
            yield data[start:end]
    require(end == len(data), 'unmapped UCAS bytes')

def decode_asset(a):
    # Recognize this exact serialized field schema, not offsets in arbitrary assets.
    if ASSET_PATH.encode() not in a:
        return None
    require(len(a) >= 0x44 and u32(a,0) == 0, 'unexpected Zen summary')
    header = u32(a,4)
    n = u32(a,52)
    require(n == 26 and header < len(a), 'unexpected name map')
    p = 0x44+8*n
    sizes = [int.from_bytes(a[p+2*i:p+2*i+2],'big') for i in range(n)]
    p += 2*n
    names=[]
    for size in sizes:
        require(0 < size <= 256 and p+size <= header, 'name bounds')
        names.append(a[p:p+size].decode('ascii')); p+=size
    require(names[-2:] == [ASSET,ASSET_PATH], 'package identity mismatch')
    require(u32(a,header+30) == len(FIELDS), 'field count mismatch')
    p = header+34
    for i, name in enumerate(FIELDS):
        ty, number, field, field_number = struct.unpack_from('<4I', a,p)
        require(number == field_number == 0 and field < len(names) and ty < len(names), 'invalid FName')
        require(re.fullmatch(re.escape(name)+r'_\d+_[0-9A-F]{32}', names[field]) is not None, 'field order mismatch')
        nested = 8 <= i < 20
        require(names[ty] == ('StructProperty' if nested else 'DoubleProperty'), 'field type mismatch')
        require(u32(a,p+24)==(16 if nested else 8), 'field size mismatch')
        p += 51 if nested else 47
    require(a[p:p+12] == b'\0'*12, 'unexpected struct suffix')
    p+=12
    require(a[p:p+2] == struct.pack('<H', (len(FIELDS)<<9)|0x180), 'unexpected default header')
    mask = u32(a,p+2);p+=6
    require(mask >> 21 == 0, 'unexpected mask padding')
    values={}
    for i,name in enumerate(FIELDS):
        if mask & (1<<i):
            values[name]=0.0 if not 8<=i<20 else 'zero-masked struct'
        elif 8<=i<20:
            # Known observed three-byte empty nested defaults. Do not decode or edit them.
            require(a[p:p+3] == b'\x80\x09\x0f', 'unknown nested default')
            values[name]='nested default';p+=3
        else:
            value=struct.unpack_from('<d',a,p)[0];p+=8
            require(math.isfinite(value), 'non-finite scalar')
            values[name]=value
    require(a[p:] == struct.pack('<I', 0x9E2A83C1), 'unexpected package trailer')
    return values

def inspect_archive(path):
    with zipfile.ZipFile(path) as z:
        entries=z.infolist()
        require(len(entries)<=128 and sum(i.file_size for i in entries)<=LIMIT, 'archive exceeds bounds')
        require(len({i.filename for i in entries})==len(entries), 'duplicate archive members')
        require(z.testzip() is None, 'archive CRC failure')
        packages={}
        for entry in entries:
            if entry.is_dir():continue
            p=PurePosixPath(entry.filename)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in entry.filename and p.suffix in ('.pak','.ucas','.utoc'), 'unexpected member')
            group=packages.setdefault(str(p.with_suffix('')), {})
            group[p.suffix]=z.read(entry)
        out={}
        for name, files in packages.items():
            require(set(files)=={'.pak','.ucas','.utoc'}, 'incomplete package')
            results=[v for a in chunks(files['.utoc'],files['.ucas']) if (v:=decode_asset(a)) is not None]
            require(len(results)==1, 'missing/ambiguous difficulty export')
            out[name]={'fields':results[0],'sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},'package_exports':u32(files['.utoc'],24)-1}
        return out

def profile(xp_raw, cash_raw, loot_raw, eridium_raw=0.0):
    """Independent raw-field intentions only; not a multiplier conversion or asset writer."""
    values=dict(CombatExperience=xp_raw,Cash=cash_raw,LootLuck=loot_raw,Eridium=eridium_raw)
    require(all(type(v) in (int,float) and 0 <= v <= 1e16 for v in values.values()), 'invalid raw values')
    return {'installable':False,'runtime_verified':False,'raw_field_intent':values}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    inspect=commands.add_parser('inspect',help='Compare supplied preset archive without writing it')
    inspect.add_argument('archive')
    plan=commands.add_parser('profile',help='Print independent RAW field intentions, not an installable mod')
    for name in ('xp','cash','loot','eridium'):
        plan.add_argument('--'+name,type=float,default=0.)
    args=p.parse_args()
    result=inspect_archive(args.archive) if args.command=='inspect' else profile(args.xp,args.cash,args.loot,args.eridium)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
