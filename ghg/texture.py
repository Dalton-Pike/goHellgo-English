"""Cooked UE4.27 Texture2D: decode mip 0 to RGBA and replace it in place (same size and format).

Only single-mip, inline textures in PF_DXT1 / PF_DXT5 / PF_B8G8R8A8 are handled (the manual pages and
chapter cards are PF_DXT1 1920x1080, one mip, inline). Replacing pixels never changes the byte count,
so the package layout stays identical.
"""
import re
import struct

import numpy as np


def locate(uexp):
    """(format, width, height, data offset, data size) of mip 0 inside a .uexp."""
    m = next(m for m in re.finditer(rb'PF_[A-Z0-9_]+\x00', uexp)
             if struct.unpack_from('<i', uexp, m.start() - 4)[0] == len(m.group()))
    fmt = m.group()[:-1].decode()
    w, h = struct.unpack_from('<ii', uexp, m.start() - 16)
    p = m.end()
    _first, nmips = struct.unpack_from('<ii', uexp, p)
    p += 8
    _cooked, flags, _count, size, _off = struct.unpack_from('<iIiiq', uexp, p)
    p += 24
    if flags & 0x101:
        raise ValueError('texture payload is not inline')
    return fmt, w, h, p, size


def _565(c):
    c = c.astype(np.int32)
    return np.stack([(c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31], -1)


def decode(uexp):
    fmt, w, h, p, size = locate(uexp)
    data = np.frombuffer(uexp, np.uint8, size, p)
    if fmt == 'PF_B8G8R8A8':
        return data.reshape(h, w, 4)[..., [2, 1, 0, 3]].copy()
    if fmt != 'PF_DXT1':
        raise ValueError(f'unsupported {fmt}')
    bw, bh = (w + 3) // 4, (h + 3) // 4
    blk = data.reshape(bh * bw, 8)
    c0 = blk[:, 0].astype(np.uint16) | blk[:, 1].astype(np.uint16) << 8
    c1 = blk[:, 2].astype(np.uint16) | blk[:, 3].astype(np.uint16) << 8
    bits = blk[:, 4:8].copy().view('<u4').ravel()
    p0, p1 = _565(c0), _565(c1)
    four = (c0 > c1)[:, None]
    p2 = np.where(four, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four, (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)                      # (n, 4, 3)
    idx = (bits[:, None] >> (2 * np.arange(16))) & 3          # (n, 16)
    px = np.take_along_axis(pal, idx[..., None].repeat(3, -1), 1)   # (n, 16, 3)
    img = px.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)[:h, :w]
    return np.concatenate([img, np.full((h, w, 1), 255)], -1).astype(np.uint8)


def encode_dxt1(rgb):
    """Range-fit DXT1 encoder (4-colour mode), vectorised over all 4x4 blocks."""
    h, w = rgb.shape[:2]
    bh, bw = (h + 3) // 4, (w + 3) // 4
    pad = np.zeros((bh * 4, bw * 4, 3), np.float32)
    pad[:h, :w] = rgb[..., :3]
    blocks = pad.reshape(bh, 4, bw, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3)
    mean = blocks.mean(1, keepdims=True)
    centered = blocks - mean
    cov = np.einsum('nki,nkj->nij', centered, centered)
    axis = np.ones((len(blocks), 3), np.float32)
    for _ in range(6):                                        # power iteration for the principal axis
        axis = np.einsum('nij,nj->ni', cov, axis)
        axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-6)
    proj = np.einsum('nki,ni->nk', centered, axis)
    lo = mean[:, 0] + axis * proj.min(1, keepdims=True)
    hi = mean[:, 0] + axis * proj.max(1, keepdims=True)

    def to565(c):
        c = np.clip(np.rint(c), 0, 255).astype(np.int32)
        return (c[:, 0] * 31 + 127) // 255 << 11 | (c[:, 1] * 63 + 127) // 255 << 5 | (c[:, 2] * 31 + 127) // 255

    a, b = to565(hi), to565(lo)
    swap = a < b
    a, b = np.where(swap, b, a), np.where(swap, a, b)
    same = a == b                                             # flat block: force 4-colour mode
    b = np.where(same & (a > 0), a - 1, b)
    a = np.where(same & (a == 0), 1, a)
    p0, p1 = _565(a).astype(np.float32), _565(b).astype(np.float32)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    dist = ((blocks[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    idx = dist.argmin(-1).astype(np.uint32)
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros((len(blocks), 8), np.uint8)
    out[:, 0], out[:, 1] = a & 255, a >> 8
    out[:, 2], out[:, 3] = b & 255, b >> 8
    out[:, 4:8] = bits.astype('<u4').view(np.uint8).reshape(-1, 4)
    return out.tobytes()


def replace(uexp, rgba):
    """Return a new .uexp with mip 0 replaced by rgba (H, W, 3/4 uint8, same size as the original)."""
    fmt, w, h, p, size = locate(uexp)
    if rgba.shape[:2] != (h, w):
        raise ValueError(f'image is {rgba.shape[1]}x{rgba.shape[0]}, texture is {w}x{h}')
    if fmt == 'PF_DXT1':
        data = encode_dxt1(rgba.astype(np.float32))
    elif fmt == 'PF_B8G8R8A8':
        img = rgba if rgba.shape[2] == 4 else np.concatenate([rgba, np.full((h, w, 1), 255, np.uint8)], -1)
        data = img[..., [2, 1, 0, 3]].astype(np.uint8).tobytes()
    else:
        raise ValueError(f'unsupported {fmt}')
    if len(data) != size:
        raise ValueError('encoded size mismatch')
    return uexp[:p] + data + uexp[p + size:]
