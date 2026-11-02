"""Apply translations to the game assets and write the English patch pak.

Run:  python3 -m ghg.build [--wrap 46]

Translation memory (all in work/tm/; fix a line by editing it here):
  dialogue/<scene>.json   {string id: English}          story lines, no manual line breaks
  other.json              {category: {Japanese: English}} names, UI, item/skill/enemy data, speaker names
Missing translations leave the Japanese text in place; the report lists them.

Output: work/dist/gohellgo-English_P.pak and work/dist/manifest.json (base-game fingerprint for the installer).
"""
import argparse
import glob
import json
import os
import re
import textwrap
from collections import Counter, defaultdict

from .common import BASE_PAK, PATCH_NAME, WORK, has_jp
from .pak import PakReader, write_pak
from .fontmetrics import Font
from . import fit
from .uasset import Package

MAX_LINES = 3
# DT_DeadFlavorTextMaster: the game glues fragments from several categories into one blurb
# (0 describer, 1 noun, 2 connector, 3 hobby, 4 predicate, 6 adverb, 7 trait). Japanese needs no
# spaces between them; English does, so every fragment after the first slot gets a leading space
# unless it starts with punctuation.
FLAVOR_TABLE = 'DT_DeadFlavorTextMaster'
ROW_CHARS = 58          # stays under the VN plugin's Text Row Count (60, set in ghg.fit), for a safety margin
ROW_EM = 32.0           # max row width in em of the dialogue font (a full Japanese row is 26 x 1.2 = 31.2 em)
DIALOGUE_FONT = 'gohellgo/Content/Anzu/Font/GenEiLateMinN_v2.ufont'
NO_SPACE_BEFORE = tuple(',.:;!?)…\'"')


def row_ints(pkg, field):
    """{row name: int value of `field`} for a DataTable package."""
    import struct as _s
    from .uasset import _R
    e = pkg.exports[0]
    r = _R(pkg.data, e['off'])
    while (t := pkg._tag(r)) is not None:
        r.p += t[2]
    r.skip(4)
    out = {}
    for _ in range(r.i32()):
        row = pkg.fname(r)
        while (t := pkg._tag(r)) is not None:
            name, ty, size = t[0], t[1], t[2]
            if ty == 'IntProperty' and name.split('_')[0] == field:
                out[row] = _s.unpack_from('<i', pkg.data, r.p)[0]
            r.p += size
    return out


def load_tm(tm_dir):
    dialogue = {}
    for path in glob.glob(os.path.join(tm_dir, 'dialogue', '*.json')):
        with open(path, encoding='utf-8') as f:
            dialogue.update(json.load(f))
    other_path = os.path.join(tm_dir, 'other.json')
    other = json.load(open(other_path, encoding='utf-8')) if os.path.exists(other_path) else {}
    return dialogue, other


def newline_style(ja):
    if '\\n' in ja:
        return '\\n'          # the scenario tables store a literal backslash-n
    if '\n' in ja:
        return '\n'
    return None


def wrap_dialogue(en, font, max_em=ROW_EM, max_chars=ROW_CHARS):
    """Word-wrap by measured glyph width (em of the dialogue font, letter spacing 0) and character count.

    Rows are joined with the scenario's literal \\n. Measuring in em keeps the layout identical at every
    resolution, because the game scales the font and the message box together."""
    words = re.sub(r'\s*(\\n|\n)\s*', ' ', en).strip().split(' ')
    rows, cur = [], ''
    for w in words:
        cand = w if not cur else cur + ' ' + w
        if cur and (font.width_em(cand) > max_em or len(cand) > max_chars):
            rows.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        rows.append(cur)
    return '\\n'.join(rows), len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--row-em', type=float, default=ROW_EM, help='max dialogue row width in em')
    ap.add_argument('--tm', default=os.path.join(WORK, 'tm'), help='translation memory folder')
    args = ap.parse_args()

    recs = [json.loads(line) for line in open(os.path.join(WORK, 'strings.jsonl'), encoding='utf-8')]
    dialogue, other = load_tm(args.tm)
    pak = PakReader(BASE_PAK)
    font_path = os.path.join(WORK, 'fonts', DIALOGUE_FONT.rsplit('/', 1)[1])
    if not os.path.exists(font_path):
        os.makedirs(os.path.dirname(font_path), exist_ok=True)
        open(font_path, 'wb').write(pak.read(DIALOGUE_FONT))
    font = Font(font_path)
    by_asset = defaultdict(list)
    stats, missing, warnings = Counter(), Counter(), []

    def english(r):
        if r['category'] == 'dialogue':
            en = dialogue.get(r['id'])
        else:
            en = fit.text_override(r) or other.get(r['category'], {}).get(r['ja'])
        return fit.rename(en) if en else en

    dung_names = {r['path'].split('.')[0]: english(r) for r in recs
                  if r['category'] == 'data:DT_DungeonMaster.Name' and english(r)}
    for r in recs:
        cat = r['category']
        if cat.startswith('keep'):
            continue
        en = english(r)
        if not en:
            missing[cat.split('.')[0]] += 1
            continue
        if cat == 'dialogue':
            en, nlines = wrap_dialogue(en, font, args.row_em)
            if nlines > MAX_LINES:
                warnings.append(f'{r["id"]}: {nlines} rows at {args.row_em} em')
        else:
            en = fit.rewrap(r, en, dung_names) or en
            style = newline_style(r['ja'])
            if style:
                en = re.sub(r'\\n|\n', style.replace('\\', '\\\\'), en)
            else:
                en = re.sub(r'\s*(\\n|\n)\s*', ' ', en)
        if has_jp(en):
            warnings.append(f'{r["id"]}: Japanese left in translation')
        if cat == 'speaker':
            en = r['prefix'] + '/' + en           # the sprite id before '/' stays as the game's lookup key
        by_asset[r['asset']].append((r, en))
        stats[cat.split('.')[0]] += 1

    files = {}
    for asset, items in sorted(by_asset.items()):
        pkg = Package(pak.read(asset + '.uasset'), pak.read(asset + '.uexp'), asset)
        vals = {(v.export, v.path): v for v in pkg.strings()}
        flavor = row_ints(pkg, 'Category') if asset.endswith('/' + FLAVOR_TABLE) else None
        repl = {}
        for r, en in items:
            v = vals[(r['export'], r['path'])]
            expected = r['ja'] if r['category'] != 'speaker' else r['prefix'] + '/' + r['ja']
            if v.text != expected:
                raise SystemExit(f'{r["id"]}: base game text changed; re-run ghg.extract')
            if flavor is not None and flavor.get(r['path'].split('.')[0].split('/', 1)[1], 0) != 0 \
                    and not en.startswith(NO_SPACE_BEFORE):
                en = ' ' + en
            repl[v.start] = en
        ua, ue = pkg.rewrite(repl)
        files[asset + '.uasset'] = ua
        files[asset + '.uexp'] = ue

    # Translated images: work/<dir>/en/<texture>.png replaces the texture of the same name (same size, DXT1).
    image_sets = [('manual', 'gohellgo/Content/Anzu/WBP/Manual/Img_Manual/', 'Manu_*.png'),
                  ('chapter', 'gohellgo/Content/Anzu/Texture/Cmn_Tex/Thumb_Chap_Title/', 'Text_Chap_Title_*.png')]
    for folder, asset_dir, pattern in image_sets:
        pngs = sorted(glob.glob(os.path.join(WORK, folder, 'en', pattern)))
        if not pngs:
            continue
        from PIL import Image                  # needs the .venv (Pillow, numpy)
        import numpy as np
        from . import texture
        done = 0
        for png in pngs:
            asset = asset_dir + os.path.basename(png)[:-4]
            if asset + '.uexp' not in pak.files:
                continue
            img = np.asarray(Image.open(png).convert('RGB'))
            files[asset + '.uasset'] = pak.read(asset + '.uasset')
            files[asset + '.uexp'] = texture.replace(pak.read(asset + '.uexp'), img)
            done += 1
        print(f'{folder} images replaced: {done}')

    def package(asset):
        if asset + '.uasset' in files:
            return Package(files[asset + '.uasset'], files[asset + '.uexp'], asset)
        return Package(pak.read(asset + '.uasset'), pak.read(asset + '.uexp'), asset)

    def store(asset, data, hsize):
        files[asset + '.uasset'] = bytes(data[:hsize])
        files[asset + '.uexp'] = bytes(data[hsize:])

    def set_int(pkg, data, export, prop, value):
        offs = pkg.int_offsets(export, prop)
        if len(offs) != 1:
            raise SystemExit(f'{pkg.name}:{export}.{".".join(prop)}: expected one value, found {len(offs)}')
        old = int.from_bytes(data[offs[0]:offs[0] + 4], 'little', signed=True)
        data[offs[0]:offs[0] + 4] = value.to_bytes(4, 'little', signed=True)
        return old

    tweaks = defaultdict(list)
    for asset, export, prop, value in fit.INTS:
        tweaks[asset].append((export, prop, value))
    for asset, items in tweaks.items():
        pkg = package(asset)
        data = bytearray(pkg.data)
        for export, prop, value in items:
            old = set_int(pkg, data, export, prop, value)
            print(f'tweak {asset.rsplit("/", 1)[1]}.{export}.{".".join(prop)}: {old} -> {value}')
        store(asset, data, pkg.total_header_size)

    # Screen titles: lower each title's letter spacing until its English fits the frame.
    for asset, items in by_asset.items():
        titles = {r['export']: en for r, en in items if re.fullmatch(r'Title_[LM]01_Text_Main', r['field'])}
        if not titles:
            continue
        pkg = package(asset)
        data = bytearray(pkg.data)
        changed = False
        for ei, en in titles.items():
            e = pkg.exports[ei]
            if e['cls'] not in fit.TITLE_WIDGETS:
                continue
            size, room = fit.TITLE_WIDGETS[e['cls']]
            prop = ['In Font Info', 'LetterSpacing']
            offs = pkg.int_offsets(e['name'], prop)
            current = int.from_bytes(data[offs[0]:offs[0] + 4], 'little', signed=True) if len(offs) == 1 else 0
            ls = fit.title_spacing(en, size, room, current)
            if ls != current:
                set_int(pkg, data, e['name'], prop, ls)
                changed = True
                print(f'title {asset.rsplit("/", 1)[1]} "{en}": letter spacing {current} -> {ls}')
            if fit.font().width_px(en, size, ls) + 12 > room:
                warnings.append(f'{asset.rsplit("/", 1)[1]}: title "{en}" is too wide even without letter spacing')
        if changed:
            store(asset, data, pkg.total_header_size)

    for asset, old, new in fit.BYTES:
        if len(old) != len(new):
            raise SystemExit(f'{asset}: bytecode patch must keep the size')
        pkg = package(asset)
        data = bytearray(pkg.data)
        if data.count(old) != 1:
            raise SystemExit(f'{asset}: expected the bytecode string once, found {data.count(old)}')
        i = data.index(old)
        data[i:i + len(old)] = new
        store(asset, data, pkg.total_header_size)
        print(f'bytecode {asset.rsplit("/", 1)[1]}: {old!r} -> {new!r}')

    warnings += fit.report(english, recs)

    dist = os.path.join(WORK, 'dist')
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, PATCH_NAME)
    write_pak(out, files)
    manifest = {
        'patch': PATCH_NAME,
        'base_pak': 'gohellgo-WindowsNoEditor.pak',
        'base_pak_size': os.path.getsize(BASE_PAK),
        'base_index_sha1': pak.index_sha1.hex(),
        'row_em': args.row_em,
        'row_chars': ROW_CHARS,
        'tm': os.path.relpath(args.tm, WORK),
        'translated': dict(stats),
        'missing': dict(missing),
    }
    json.dump(manifest, open(os.path.join(dist, 'manifest.json'), 'w'), indent=2)
    print(f'wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB, {len(files)} files)')
    print('translated:', dict(stats))
    print('still Japanese:', dict(missing))
    if warnings:
        print(f'{len(warnings)} warnings (first 15):')
        for w in warnings[:15]:
            print('  ', w)


if __name__ == '__main__':
    main()
