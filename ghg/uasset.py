"""Cooked UE 4.27 packages (.uasset + .uexp, tagged properties): find string values and rewrite them.

Every string found is recorded with its byte span and the offsets of all property-size fields that
enclose it, so a rewrite can change string lengths and fix every size and offset that depends on
them: property tag sizes, inner array tags, export SerialSize/SerialOffset and BulkDataStartOffset.
"""
import struct
from collections import defaultdict
from dataclasses import dataclass

from .pak import read_fstring, write_fstring

PACKAGE_TAG = 0x9E2A83C1
PKG_UNVERSIONED_PROPS = 0x2000
EXPORT_ENTRY_SIZE = 104

# Structs serialized natively (not as tagged properties); they never hold text we translate.
NATIVE_STRUCTS = {
    'Vector', 'Vector2D', 'Vector4', 'Rotator', 'Quat', 'Color', 'LinearColor', 'Guid', 'IntPoint', 'IntVector',
    'Box', 'Box2D', 'DateTime', 'Timespan', 'SoftObjectPath', 'SoftClassPath', 'GameplayTagContainer', 'GameplayTag',
    'Transform', 'Margin', 'FrameNumber', 'PerPlatformFloat', 'PerPlatformInt', 'RichCurveKey', 'SimpleCurveKey',
    'SlateColor', 'FontData', 'SlateBrush', 'MovieSceneFloatChannel', 'MovieSceneFrameRange', 'NavAgentSelector',
    'Plane', 'Matrix', 'Sphere', 'ColorMaterialInput', 'ScalarMaterialInput', 'VectorMaterialInput',
    'ExpressionInput', 'MaterialAttributesInput',
}

# Exports whose payload stores absolute file offsets; rewriting before them would break the package.
OFFSET_SENSITIVE = {'Texture2D', 'TextureCube', 'SoundWave', 'StaticMesh', 'SkeletalMesh', 'AnimSequence',
                    'FontFace', 'Font', 'MediaTexture', 'TextureRenderTarget2D', 'NiagaraSystem'}


@dataclass
class StrValue:
    export: int        # export index, 0-based
    path: str          # property path inside the export, e.g. "Main0101/16.TEXT_24_C669..."
    kind: str          # 'Text' (FText) or 'Str' (FString)
    text: str
    start: int         # absolute offset of the serialized FString that holds the text
    end: int
    sizes: tuple       # absolute offsets of every int32 size field enclosing the value
    ns: str = None     # FText namespace/key (base history only)
    key: str = None
    history: str = None


class _R:
    __slots__ = ('b', 'p')

    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def i32(self):
        v = struct.unpack_from('<i', self.b, self.p)[0]
        self.p += 4
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.b, self.p)[0]
        self.p += 4
        return v

    def i64(self):
        v = struct.unpack_from('<q', self.b, self.p)[0]
        self.p += 8
        return v

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def skip(self, n):
        self.p += n

    def fstr(self):
        s, self.p = read_fstring(self.b, self.p)
        return s


class ParseError(Exception):
    pass


class Package:
    def __init__(self, uasset: bytes, uexp: bytes, name='', header_only=False):
        self.name = name
        self.data = uasset + uexp
        self.header_size_actual = len(uasset)
        r = _R(self.data)
        if r.u32() != PACKAGE_TAG:
            raise ParseError('not a package')
        legacy = r.i32()
        if legacy != -7:
            raise ParseError(f'unexpected legacy version {legacy}')
        r.i32()                                  # legacy UE3 version
        r.i32()                                  # UE4 version (0 = unversioned, i.e. current)
        r.i32()                                  # licensee version
        r.skip(20 * r.i32())                     # custom versions
        self.total_header_size = r.i32()
        r.fstr()                                 # folder name
        self.package_flags = r.u32()
        if self.package_flags & PKG_UNVERSIONED_PROPS:
            raise ParseError('unversioned property serialization is not supported')
        name_count, name_off = r.i32(), r.i32()
        r.skip(8)                                # gatherable text data count/offset (cooked: empty)
        export_count, self.export_off = r.i32(), r.i32()
        import_count, import_off = r.i32(), r.i32()
        r.skip(4 * 5)                            # depends, soft package refs count/offset, searchable names, thumbnails
        r.skip(16)                               # package guid
        r.skip(8 * r.i32())                      # generations
        for _ in range(2):                       # saved-by and compatible-with engine versions
            r.skip(2 * 3 + 4)
            r.fstr()
        r.skip(4)                                # compression flags
        if r.i32() != 0:
            raise ParseError('compressed chunks not supported')
        r.skip(4)                                # package source
        for _ in range(r.i32()):                 # additional packages to cook
            r.fstr()
        r.skip(4)                                # asset registry data offset
        self.bulk_start_pos = r.p
        self.bulk_start = r.i64()
        r.skip(4)                                # world tile info
        r.skip(4 * r.i32())                      # chunk ids
        r.skip(8)                                # preload dependency count/offset
        if self.total_header_size != len(uasset):
            raise ParseError('header size does not match .uasset size')

        rn = _R(self.data, name_off)
        self.names = []
        for _ in range(name_count):
            self.names.append(rn.fstr())
            rn.skip(4)
        ri = _R(self.data, import_off)
        self.imports = []
        for _ in range(import_count):
            self.fname(ri)
            class_name = self.fname(ri)
            ri.skip(4)
            self.imports.append((class_name, self.fname(ri)))
        self.exports = []
        for i in range(export_count):
            re_ = _R(self.data, self.export_off + i * EXPORT_ENTRY_SIZE)
            cls = re_.i32()
            re_.skip(12)
            name = self.fname(re_)
            flags = re_.u32()
            size, off = re_.i64(), re_.i64()
            self.exports.append({'cls_index': cls, 'name': name, 'flags': flags, 'size': size, 'off': off})
        for e in self.exports:
            e['cls'] = self.object_name(e['cls_index'])
        if header_only:
            return
        ends = sorted((e['off'], e['off'] + e['size']) for e in self.exports)
        if ends and (ends[0][0] != self.total_header_size or ends[-1][1] + 4 != len(self.data)):
            raise ParseError('exports do not fill the .uexp')
        if struct.unpack_from('<I', self.data, len(self.data) - 4)[0] != PACKAGE_TAG:
            raise ParseError('missing .uexp end tag')

    # -- names ---------------------------------------------------------------------------------------
    def fname(self, r):
        i, n = r.i32(), r.i32()
        if not 0 <= i < len(self.names):
            raise ParseError(f'bad name index {i}')
        return self.names[i] if n == 0 else f'{self.names[i]}_{n - 1}'

    def object_name(self, idx):
        if idx < 0:
            return self.imports[-idx - 1][1]
        if idx > 0:
            return self.exports[idx - 1]['name']
        return None

    # -- reading -------------------------------------------------------------------------------------
    def _tag(self, r):
        name = self.fname(r)
        if name == 'None':
            return None
        ty = self.fname(r)
        size_pos = r.p
        size = r.i32()
        r.skip(4)                                # array index
        ext = {}
        if ty == 'StructProperty':
            ext['struct'] = self.fname(r)
            r.skip(16)
        elif ty == 'BoolProperty':
            r.skip(1)
        elif ty in ('ByteProperty', 'EnumProperty'):
            self.fname(r)
        elif ty in ('ArrayProperty', 'SetProperty'):
            ext['inner'] = self.fname(r)
        elif ty == 'MapProperty':
            ext['key'] = self.fname(r)
            ext['value'] = self.fname(r)
        if r.u8():
            r.skip(16)
        return name, ty, size, ext, size_pos

    def _string(self, r, ei, path, kind, sizes, out, **meta):
        start = r.p
        text = r.fstr()
        out.append(StrValue(ei, path, kind, text, start, r.p, sizes, **meta))

    def _text(self, r, ei, path, sizes, out):
        """FText. Returns False if the history type can't be walked (caller must rely on a tag size)."""
        r.u32()                                  # flags
        history = struct.unpack('<b', bytes([r.u8()]))[0]
        if history == -1:
            if r.i32():
                self._string(r, ei, path, 'Text', sizes, out, history='none')
            return True
        if history == 0:
            ns, key = r.fstr(), r.fstr()
            self._string(r, ei, path, 'Text', sizes, out, ns=ns, key=key, history='base')
            return True
        return False

    def _value(self, r, ei, ty, ext, path, sizes, out, tagged=True):
        """Read one value. For untagged (array/map element) values returns False if it can't be walked."""
        if ty == 'TextProperty':
            return self._text(r, ei, path, sizes, out)
        if ty == 'StrProperty':
            self._string(r, ei, path, 'Str', sizes, out)
            return True
        if ty == 'NameProperty':
            r.skip(8)
            return True
        if ty in ('IntProperty', 'UInt32Property', 'FloatProperty'):
            r.skip(4)
            return True
        if ty in ('Int64Property', 'UInt64Property', 'DoubleProperty'):
            r.skip(8)
            return True
        if ty in ('ObjectProperty', 'SoftObjectProperty') and not tagged:
            if ty == 'ObjectProperty':
                r.skip(4)
                return True
            return False
        if ty == 'StructProperty' and tagged:
            if ext.get('struct') in NATIVE_STRUCTS:
                return True
            self._props(r, ei, path, sizes, out)
            return True
        if ty == 'ArrayProperty' and tagged:
            n = r.i32()
            inner = ext['inner']
            if inner == 'StructProperty':
                itag = self._tag(r)
                if itag is None or itag[3].get('struct') in NATIVE_STRUCTS:
                    return True
                inner_sizes = sizes + (itag[4],)
                for i in range(n):
                    self._props(r, ei, f'{path}[{i}]', inner_sizes, out)
                return True
            for i in range(n):
                if not self._value(r, ei, inner, {}, f'{path}[{i}]', sizes, out, tagged=False):
                    return True
            return True
        if ty == 'MapProperty' and tagged:
            r.skip(4)                            # keys to remove
            n = r.i32()
            kt, vt = ext['key'], ext['value']
            for i in range(n):
                keys = []                        # map keys are lookup ids: walked but never offered for translation
                if not self._value(r, ei, kt, {}, f'{path}{{key}}', sizes, keys, tagged=False):
                    return True
                label = keys[0].text if keys else i
                if vt == 'StructProperty':
                    self._props(r, ei, f'{path}{{{label}}}', sizes, out)
                elif not self._value(r, ei, vt, {}, f'{path}{{{label}}}', sizes, out, tagged=False):
                    return True
            return True
        return tagged

    def _props(self, r, ei, path, sizes, out):
        while True:
            tag = self._tag(r)
            if tag is None:
                return
            name, ty, size, ext, size_pos = tag
            start = r.p
            mark = len(out)
            try:
                self._value(r, ei, ty, ext, f'{path}.{name}', sizes + (size_pos,), out)
            except (ParseError, struct.error, UnicodeDecodeError, IndexError):
                del out[mark:]                   # discard anything from a value we couldn't walk
            if any(v.end > start + size for v in out[mark:]):
                del out[mark:]
            r.p = start + size

    def strings(self):
        """All FText/FString values reachable through tagged properties, DataTable rows included."""
        if hasattr(self, '_strings'):
            return self._strings
        out = []
        for ei, e in enumerate(self.exports):
            r = _R(self.data, e['off'])
            end = e['off'] + e['size']
            mark = len(out)
            try:
                self._props(r, ei, e['name'], (), out)
                if e['cls'] == 'DataTable':
                    r.skip(4)                    # object guid flag
                    for _ in range(r.i32()):
                        row = self.fname(r)
                        self._props(r, ei, f'{e["name"]}/{row}', (), out)
                if r.p > end:
                    raise ParseError('read past export end')
            except (ParseError, struct.error, UnicodeDecodeError, IndexError):
                del out[mark:]
        self._strings = out
        return out

    def int_offsets(self, export_name, prop_path):
        """Absolute offsets of IntProperty values at prop_path (e.g. ['Font', 'LetterSpacing']) in an export."""
        found = []

        def walk(r, end, path):
            while r.p < end:
                tag = self._tag(r)
                if tag is None:
                    return
                name, ty, size, ext, _ = tag
                start = r.p
                here = path + [name.split('_')[0] if '_' in name and len(name) > 40 else name]
                if ty == 'StructProperty' and ext.get('struct') not in NATIVE_STRUCTS:
                    walk(_R(self.data, start), start + size, here)
                elif ty == 'IntProperty' and here == prop_path:
                    found.append(start)
                r.p = start + size

        for e in self.exports:
            if e['name'] == export_name:
                walk(_R(self.data, e['off']), e['off'] + e['size'], [])
        return found

    # -- writing -------------------------------------------------------------------------------------
    def rewrite(self, replacements):
        """replacements: {StrValue.start: new_text}. Returns (uasset_bytes, uexp_bytes)."""
        by_start = {v.start: v for v in self.strings()}
        edits = []
        for start, new in replacements.items():
            v = by_start[start]
            edits.append((v, write_fstring(new)))
        edits.sort(key=lambda x: x[0].start)
        if not edits:
            return self.data[:self.total_header_size], self.data[self.total_header_size:]
        first = edits[0][0].start
        for e in self.exports:
            if e['off'] > first and e['cls'] in OFFSET_SENSITIVE:
                raise ParseError(f'{self.name}: export {e["name"]} ({e["cls"]}) stores file offsets')
        size_delta = defaultdict(int)
        export_delta = defaultdict(int)
        for v, nb in edits:
            if v.start < self.total_header_size:
                raise ParseError('string inside package header')
            d = len(nb) - (v.end - v.start)
            for sp in v.sizes:
                size_delta[sp] += d
            export_delta[v.export] += d
        data = bytearray(self.data)
        for sp, d in size_delta.items():
            struct.pack_into('<i', data, sp, struct.unpack_from('<i', data, sp)[0] + d)
        order = sorted(range(len(self.exports)), key=lambda i: self.exports[i]['off'])
        shift = 0
        for i in order:
            base = self.export_off + i * EXPORT_ENTRY_SIZE
            e = self.exports[i]
            struct.pack_into('<qq', data, base + 28, e['size'] + export_delta[i], e['off'] + shift)
            shift += export_delta[i]
        struct.pack_into('<q', data, self.bulk_start_pos, self.bulk_start + shift)
        for v, nb in reversed(edits):
            data[v.start:v.end] = nb
        data = bytes(data)
        return data[:self.total_header_size], data[self.total_header_size:]
