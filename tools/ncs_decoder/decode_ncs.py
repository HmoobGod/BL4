"""Offline bounded NCS frame decoder. No game/asset writes. Public framing facts:
monokrome/bl4 6f886674f1860a65132102af1b9710f8e3db771a, src/bl4-ncs/src/data.rs.
The ZIP reader accepts one hash-pinned private PAK; no private data is bundled.
"""
import argparse
import hashlib
import pathlib
import struct
import subprocess
import zipfile

MAX = 16 * 1024 * 1024
BLOCK = 0x40000


def frame(data, raw_multi_blocks=()):
    raw_multi_blocks=tuple(raw_multi_blocks)
    if len(set(raw_multi_blocks))!=len(raw_multi_blocks) or any(type(i) is not int or i<0 for i in raw_multi_blocks):
        raise ValueError("invalid explicit raw block indices")
    if len(data) < 16 or data[:4] != b'\x01NCS':
        raise ValueError('unsupported NCS header')
    flag, raw, stored = struct.unpack_from('<III', data, 4)
    if not 0 < raw <= MAX or not 0 < stored <= MAX or len(data) != 16 + stored:
        raise ValueError('invalid NCS size or trailing bytes')
    inner = data[16:]
    if flag == 0:
        if raw_multi_blocks:raise ValueError("raw block indices require multi-block framing")
        if raw != stored:
            raise ValueError('raw size mismatch')
        return [(inner, raw, False)]
    if flag not in (1, 2, 3) or len(inner) < 64 or inner[:4] != b'\xb7\x75\x63\x62':
        raise ValueError('unsupported compressed frame')
    flags, count = struct.unpack_from('>II', inner, 8)
    if flags == 0:
        if raw_multi_blocks:raise ValueError("raw block indices require multi-block framing")
        if raw > BLOCK or count != 1:
            raise ValueError('unsupported single block')
        blob = inner[64:]
        if not blob:
            raise ValueError('empty block')
        return [(blob, raw, len(blob) != raw)]
    if flags != 0x03030812 or count != (raw + BLOCK - 1) // BLOCK:
        raise ValueError('unsupported multi-block layout')
    if any(i>=count for i in raw_multi_blocks):raise ValueError("raw block index outside table")
    start = 64 + 4 * count
    if start > len(inner):
        raise ValueError('truncated table')
    result = []
    remaining = raw
    for i in range(count):
        size = struct.unpack_from('>I', inner, 64 + 4*i)[0]
        expected = min(remaining, BLOCK)
        if not 0 < size <= expected + 65536 or start + size > len(inner):
            raise ValueError('invalid block size')
        raw_block=i in raw_multi_blocks
        if raw_block and size!=expected:raise ValueError("explicit raw block size mismatch")
        result.append((inner[start:start+size], expected, not raw_block))
        start += size
        remaining -= expected
    if start != len(inner) or remaining != 0:
        raise ValueError('incomplete or trailing compressed payload')
    return result


def extract_pinned_zip(path, digest):
    path = pathlib.Path(path)
    if path.stat().st_size > MAX:
        raise ValueError('archive too large')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest.lower():
        raise ValueError('archive hash mismatch')
    import io
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) != 1 or not members[0].filename.lower().endswith('.pak') or members[0].file_size > MAX:
            raise ValueError('expected a single bounded PAK')
        pak = archive.read(members[0])
    marker = b'\x01NCS'
    start = pak.find(marker)
    if start < 0 or pak.find(marker, start+4) != -1 or start+16 > len(pak):
        raise ValueError('ambiguous or missing NCS frame')
    size = struct.unpack_from('<I', pak, start+12)[0]
    if not 0 < size <= MAX or start+16+size > len(pak):
        raise ValueError('truncated frame')
    data = pak[start:start+16+size]
    frame(data)
    return data


def decode(data, decoder, raw_multi_blocks=()):
    parts = []
    for block, expected, compressed in frame(data, raw_multi_blocks):
        if compressed:
            r = subprocess.run([str(pathlib.Path(decoder).resolve()), 'decompress', str(expected)], input=block,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=True)
            out = r.stdout
        else:
            out = block
        if len(out) != expected:
            raise ValueError('decoder output size mismatch')
        parts.append(out)
    return b''.join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--decoder', required=True, type=pathlib.Path)
    p.add_argument('--zip-sha256', help='Required for one-PAK ZIP input')
    p.add_argument('--raw-multi-block', type=int, action='append', default=[], help='Explicit zero-based raw block; requires equal stored/output size. Validate decoded records separately.')
    args = p.parse_args()
    if args.input.suffix.lower() == '.zip':
        if not args.zip_sha256:
            p.error('ZIP input requires --zip-sha256')
        data = extract_pinned_zip(args.input, args.zip_sha256)
    else:
        if args.input.stat().st_size > MAX+16:
            raise ValueError('frame too large')
        data = args.input.read_bytes()
    out = decode(data, args.decoder, args.raw_multi_block)
    with args.output.open('xb') as f:
        f.write(out)
    print('Decoded', len(out), 'bytes; SHA256', hashlib.sha256(out).hexdigest())

if __name__ == '__main__':
    main()
