"""Extract every Japanese string the patch may translate into work/strings.jsonl.

Run:  python3 -m ghg.extract            (reads the base pak read-only)

Each line is one string:
  id        stable id: <asset>#<export>:<property path>
  asset     pak path without extension
  export    export index; path: property path inside the export
  type      Text (FText) | Str (FString)
  field     property name without GUID suffix
  category  dialogue | speaker | ui | data:<Table>.<Field> | keep:<reason>
  ja        the Japanese text to translate (for speaker overrides: only the part after '/')
  prefix    for speaker overrides: the sprite id kept in front of '/'
  scene, seq, speaker, speaker_ja   dialogue context
"""
import json
import os
import re
import sys
from collections import Counter

from .common import BASE_PAK, WORK, field_name, has_jp
from .pak import PakReader
from .uasset import Package, ParseError

SCAN_PREFIXES = (
    'gohellgo/Content/Anzu/DataTable/',
    'gohellgo/Content/Anzu/WBP/',
    'gohellgo/Content/Anzu/BP/',
    'gohellgo/Plugins/VN_Plugin/Content/VN_Plus/BluePrint/',
    'gohellgo/Plugins/VN_Plugin/Content/VN_Plus/DataTable/',
)
TEXT_CLASSES = {'DataTable', 'WidgetBlueprintGeneratedClass', 'BlueprintGeneratedClass'}
SCENARIO = 'gohellgo/Content/Anzu/DataTable/Scenario/'
SKIP_ASSETS = re.compile(r'Scenario/TestAdv|VN_Plus/DataTable/Script/scenario/|/Debug')
# Fields that hold developer notes or lookup ids rather than on-screen text.
KEEP_FIELDS = {'Comment', 'Debug_String', 'DataValue'}
KEEP_TABLE_FIELDS = {
    ('DT_AnzuScenarioMaster', 'Description'),   # developer progress notes
    ('DT_EnemyMaster', 'Description'),          # "zombie type (scratch) strength 1" style dev notes
    ('DT_DeadMaster', 'Description'),           # "test data A"
}
# Strings other tables or the script use as lookup keys: translating them would break the game.
ID_TABLE_FIELDS = {
    ('DT_Character', 'CharacterName'),          # sprite id that scenario Arg1 points at, e.g. 灯A1
    ('DT_BuffMaster', 'Name'),
}
TRANSLATE_COMMENT_TABLES = {'DT_ItemMaster'}       # its Comment is the item effect line shown in menus
SPRITE_SUFFIX = re.compile(r'[A-Z]\d+$')


def classify(asset, field, table):
    if SKIP_ASSETS.search(asset):
        return 'keep:debug'
    if asset.startswith(SCENARIO):
        if field == 'TEXT':
            return 'dialogue'
        if field == 'Arg1':
            return 'speaker'
        return 'keep:script'
    if (table, field) in ID_TABLE_FIELDS:
        return 'keep:id'
    if (table, field) in KEEP_TABLE_FIELDS:
        return 'keep:devnote'
    if field in KEEP_FIELDS and table not in TRANSLATE_COMMENT_TABLES:
        return 'keep:devnote'
    if '/DataTable/' in asset:
        return f'data:{table}.{field}'
    return 'ui'


def scenario_rows(values):
    """Group a scenario DataTable's strings by row: {row: {field: StrValue}} in file order."""
    rows = {}
    for v in values:
        row = v.path.split('.')[0].split('/', 1)[1]
        rows.setdefault(row, {})[field_name(v.path)] = v
    return rows


def main():
    os.makedirs(WORK, exist_ok=True)
    pak = PakReader(BASE_PAK)
    out, stats, failed = [], Counter(), []
    assets = sorted(n[:-7] for n in pak.files if n.endswith('.uasset') and n.startswith(SCAN_PREFIXES))
    for asset in assets:
        ua = pak.read(asset + '.uasset')
        try:
            head = Package(ua, b'', asset, header_only=True)
        except ParseError as e:
            failed.append((asset, str(e)))
            continue
        if not any(e['cls'] in TEXT_CLASSES for e in head.exports):
            continue
        try:
            pkg = Package(ua, pak.read(asset + '.uexp'), asset)
        except ParseError as e:
            failed.append((asset, str(e)))
            continue
        values = pkg.strings()
        table = asset.rsplit('/', 1)[1]
        if table == 'DT_Character':               # full sprite id -> display name map, for speaker labels
            rows = {}
            for v in values:
                rows.setdefault(v.path.split('.')[0], {})[field_name(v.path)] = v.text
            characters = {f['CharacterName']: f.get('DisplayName', '') for f in rows.values() if 'CharacterName' in f}
            with open(os.path.join(WORK, 'characters.json'), 'w', encoding='utf-8') as f:
                json.dump(characters, f, ensure_ascii=False, indent=1)
        is_scenario = asset.startswith(SCENARIO)
        rows = scenario_rows(values) if is_scenario else {}
        row_seq = {r: i for i, r in enumerate(rows)}
        for v in values:
            if not has_jp(v.text):
                continue
            field = field_name(v.path)
            cat = classify(asset, field, table)
            rec = {'id': f'{asset}#{v.export}:{v.path}', 'asset': asset, 'export': v.export, 'path': v.path,
                   'type': v.kind, 'field': field, 'category': cat, 'ja': v.text}
            if cat == 'speaker':
                if '/' not in v.text:
                    continue                      # a bare sprite id: nothing shown on screen
                rec['prefix'], rec['ja'] = v.text.split('/', 1)
            if is_scenario and not cat.startswith('keep'):
                row = v.path.split('.')[0].split('/', 1)[1]
                arg1 = rows[row].get('Arg1')
                sprite = arg1.text.split('/', 1)[0] if arg1 else ''
                rec.update(scene=table, seq=row_seq[row], row=row, sprite=sprite,
                           speaker=SPRITE_SUFFIX.sub('', sprite) if sprite else '',
                           speaker_ja=arg1.text.split('/', 1)[1] if arg1 and '/' in arg1.text else '')
            out.append(rec)
            stats[cat if not cat.startswith('data:') else 'data'] += 1
    path = os.path.join(WORK, 'strings.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(f'wrote {len(out)} strings to {path}')
    for k, n in sorted(stats.items()):
        print(f'  {k:16} {n}')
    if failed:
        print(f'{len(failed)} assets could not be parsed:', file=sys.stderr)
        for a, e in failed[:20]:
            print('  ', a, e, file=sys.stderr)


if __name__ == '__main__':
    main()
