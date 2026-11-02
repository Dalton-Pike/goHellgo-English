"""Unreal Engine pak files, version 11 (UE 4.26/4.27).

PakReader only ever opens the source pak for reading. write_pak builds a new, uncompressed
pak with the same index layout UnrealPak produces: a primary index, a path-hash index (with
the pruned directory index after it) and a full directory index. The layout was checked
against the base Go Hell Go pak.
"""
import hashlib
import os
import struct
import zlib

PAK_MAGIC = 0x5A6F12E1
PAK_VERSION = 11
FOOTER_SIZE = 16 + 1 + 4 + 4 + 8 + 8 + 20 + 5 * 32  # key guid, encrypted flag, magic, version, index off/size, sha1, compression names


def read_fstring(buf, pos):
    """Read an FString at pos; returns (text, new_pos)."""
    n = struct.unpack_from('<i', buf, pos)[0]
    pos += 4
    if n == 0:
        return '', pos
    if n > 0:
        return buf[pos:pos + n - 1].decode('latin-1'), pos + n
    n = -n
    return buf[pos:pos + 2 * n - 2].decode('utf-16-le'), pos + 2 * n


def write_fstring(text):
    """Serialize like FString::operator<<: pure ASCII as ANSI, anything else as UTF-16, empty as length 0."""
    if not text:
        return struct.pack('<i', 0)
    if all(ord(c) < 0x80 for c in text):
        raw = text.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    raw = text.encode('utf-16-le') + b'\0\0'
    return struct.pack('<i', -(len(raw) // 2)) + raw


def path_hash(path, seed):
    """FPakFile::HashPath for pak v11: FNV-64 over the lowercased UTF-16 path, offset basis plus seed."""
    h = (0xCBF29CE484222325 + seed) & 0xFFFFFFFFFFFFFFFF
    for byte in path.lower().encode('utf-16-le'):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


class PakReader:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        size = os.path.getsize(path)
        self.f.seek(size - FOOTER_SIZE)
        footer = self.f.read(FOOTER_SIZE)
        if footer[16] != 0:
            raise ValueError('pak index is encrypted')
        magic, version, ioff, isize = struct.unpack_from('<IIqq', footer, 17)
        if magic != PAK_MAGIC or version != PAK_VERSION:
            raise ValueError(f'unsupported pak (magic {magic:#x}, version {version})')
        self.index_sha1 = footer[41:61]
        names = footer[61:]
        self.methods = ['None'] + [names[i:i + 32].rstrip(b'\0').decode() for i in range(0, 160, 32)]
        self.f.seek(ioff)
        idx = self.f.read(isize)
        if hashlib.sha1(idx).digest() != self.index_sha1:
            raise ValueError('pak index hash mismatch')
        p = 0
        self.mount, p = read_fstring(idx, p)
        self.count, self.seed = struct.unpack_from('<iQ', idx, p)
        p += 12
        if struct.unpack_from('<I', idx, p)[0]:
            p += 4 + 16 + 20
        else:
            p += 4
        if not struct.unpack_from('<I', idx, p)[0]:
            raise ValueError('pak has no full directory index')
        fdoff, fdsize = struct.unpack_from('<qq', idx, p + 4)
        p += 4 + 16 + 20
        n = struct.unpack_from('<i', idx, p)[0]
        p += 4
        self.encoded = idx[p:p + n]
        self.f.seek(fdoff)
        fd = self.f.read(fdsize)
        q = 4
        self.files = {}
        for _ in range(struct.unpack_from('<i', fd, 0)[0]):
            d, q = read_fstring(fd, q)
            nf = struct.unpack_from('<i', fd, q)[0]
            q += 4
            for _ in range(nf):
                name, q = read_fstring(fd, q)
                self.files[d + name] = struct.unpack_from('<i', fd, q)[0]
                q += 4

    def entry(self, name):
        b, p = self.encoded, self.files[name]
        v = struct.unpack_from('<I', b, p)[0]
        p += 4
        if (v & 0x3F) == 0x3F:
            p += 4
        method = (v >> 23) & 0x3F

        def num(bit):
            nonlocal p
            if v & (1 << bit):
                x = struct.unpack_from('<I', b, p)[0]
                p += 4
            else:
                x = struct.unpack_from('<q', b, p)[0]
                p += 8
            return x

        offset, usize = num(31), num(30)
        size = num(29) if method else usize
        return {'offset': offset, 'usize': usize, 'size': size, 'method': self.methods[method],
                'encrypted': bool(v & (1 << 22))}

    def read(self, name):
        e = self.entry(name)
        if e['encrypted']:
            raise ValueError(f'{name} is encrypted')
        self.f.seek(e['offset'])
        _, size, usize, method = struct.unpack('<qqqI', self.f.read(28))
        self.f.read(20)
        if method == 0:
            self.f.read(5)
            return self.f.read(usize)
        blocks = [struct.unpack('<qq', self.f.read(16)) for _ in range(struct.unpack('<i', self.f.read(4))[0])]
        out = bytearray()
        for start, end in blocks:
            self.f.seek(e['offset'] + start)
            out += zlib.decompress(self.f.read(end - start))
        if len(out) != usize:
            raise ValueError(f'{name}: decompressed size mismatch')
        return bytes(out)


def write_pak(out_path, files, mount='../../../'):
    """Write an uncompressed v11 pak holding files ({path relative to mount: bytes})."""
    seed = zlib.crc32(os.path.basename(out_path).lower().encode())
    paths = sorted(files)
    tmp = out_path + '.part'
    with open(tmp, 'wb') as f:
        enc = bytearray()
        enc_off = {}
        for path in paths:
            data = files[path]
            off = f.tell()
            if off >= 2 ** 32 or len(data) >= 2 ** 32:
                raise ValueError('patch pak too large for 32-bit encoded entries')
            f.write(struct.pack('<qqqI', 0, len(data), len(data), 0) + hashlib.sha1(data).digest() + b'\0' + struct.pack('<I', 0))
            f.write(data)
            enc_off[path] = len(enc)
            enc += struct.pack('<III', 0xE0000000, off, len(data))

        dirs = {'/': {}}
        for path in paths:
            d, name = path.rsplit('/', 1)
            dirs.setdefault(d + '/', {})[name] = enc_off[path]
            parts = d.split('/')
            for i in range(1, len(parts)):
                dirs.setdefault('/'.join(parts[:i]) + '/', {})
        fd = bytearray(struct.pack('<i', len(dirs)))
        for d in sorted(dirs):
            fd += write_fstring(d) + struct.pack('<i', len(dirs[d]))
            for name in sorted(dirs[d]):
                fd += write_fstring(name) + struct.pack('<i', dirs[d][name])
        fd = bytes(fd)
        # Path-hash index, then the pruned directory index (we keep everything, so it equals the full one).
        ph = struct.pack('<i', len(paths)) + b''.join(struct.pack('<Qi', path_hash(p, seed), enc_off[p]) for p in paths) + fd

        index_off = f.tell()

        def primary(ph_off, fd_off):
            return (write_fstring(mount) + struct.pack('<iQ', len(paths), seed)
                    + struct.pack('<Iqq', 1, ph_off, len(ph)) + hashlib.sha1(ph).digest()
                    + struct.pack('<Iqq', 1, fd_off, len(fd)) + hashlib.sha1(fd).digest()
                    + struct.pack('<i', len(enc)) + bytes(enc) + struct.pack('<i', 0))

        isize = len(primary(0, 0))
        idx = primary(index_off + isize, index_off + isize + len(ph))
        f.write(idx)
        f.write(ph)
        f.write(fd)
        names = b'Zlib'.ljust(32, b'\0') + b'\0' * 128
        f.write(b'\0' * 17 + struct.pack('<IIqq', PAK_MAGIC, PAK_VERSION, index_off, len(idx)) + hashlib.sha1(idx).digest() + names)
    os.replace(tmp, out_path)
