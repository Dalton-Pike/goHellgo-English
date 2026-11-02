"""Glyph advance widths from a TrueType/OpenType font (cmap + hmtx), for width-aware line wrapping."""
import struct


class Font:
    def __init__(self, path):
        d = self.d = open(path, 'rb').read()
        n = struct.unpack_from('>H', d, 4)[0]
        self.tables = {d[12 + 16 * i:16 + 16 * i].decode('latin-1'): struct.unpack_from('>II', d, 20 + 16 * i)
                       for i in range(n)}
        self.upem = struct.unpack_from('>H', d, self.tables['head'][0] + 18)[0]
        hh = self.tables['hhea'][0]
        asc, desc, gap = struct.unpack_from('>hhh', d, hh + 4)
        self.line_em = (asc - desc + gap) / self.upem   # FreeType face height: Slate's letter-spacing unit
        nh = struct.unpack_from('>H', d, hh + 34)[0]
        ho = self.tables['hmtx'][0]
        self.adv = [struct.unpack_from('>H', d, ho + 4 * i)[0] for i in range(nh)]
        self.cmap = self._cmap()

    def _cmap(self):
        d, base = self.d, self.tables['cmap'][0]
        best = None
        for i in range(struct.unpack_from('>H', d, base + 2)[0]):
            pid, eid, off = struct.unpack_from('>HHI', d, base + 4 + 8 * i)
            fmt = struct.unpack_from('>H', d, base + off)[0]
            if fmt == 12 or (fmt == 4 and best is None):
                best = (fmt, base + off)
        fmt, o = best
        m = {}
        if fmt == 12:
            for g in range(struct.unpack_from('>I', d, o + 12)[0]):
                s, e, gid = struct.unpack_from('>III', d, o + 16 + 12 * g)
                for c in range(s, e + 1):
                    m[c] = gid + c - s
        else:
            seg = struct.unpack_from('>H', d, o + 6)[0] // 2
            ends = struct.unpack_from(f'>{seg}H', d, o + 14)
            starts = struct.unpack_from(f'>{seg}H', d, o + 16 + 2 * seg)
            deltas = struct.unpack_from(f'>{seg}h', d, o + 16 + 4 * seg)
            ro = o + 16 + 6 * seg
            ranges = struct.unpack_from(f'>{seg}H', d, ro)
            for i in range(seg):
                for c in range(starts[i], ends[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if ranges[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        gi = ro + 2 * i + ranges[i] + 2 * (c - starts[i])
                        g = struct.unpack_from('>H', d, gi)[0]
                        g = (g + deltas[i]) & 0xFFFF if g else 0
                    m[c] = g
        return m

    def advance_em(self, ch):
        g = self.cmap.get(ord(ch), 0)
        return self.adv[min(g, len(self.adv) - 1)] / self.upem

    def width_em(self, text, spacing_em=0.0):
        return sum(self.advance_em(c) + spacing_em for c in text)

    def width_px(self, text, size, letter_spacing=0):
        """Advance width in UMG design pixels of one line, the trailing letter spacing excluded.

        Glyphs render at size * 96/72 px per em; LetterSpacing is 1/1000 of the font's line height
        taken at `size` px (no DPI factor). Both were fitted against in-game screenshots."""
        em = size * 96 / 72
        spacing = letter_spacing / 1000 * self.line_em * size
        return sum(self.advance_em(c) * em for c in text) + spacing * max(len(text) - 1, 0)
