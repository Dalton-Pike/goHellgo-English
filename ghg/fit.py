"""Make English fit the game's menus: per-widget wording, font tweaks, re-wrapping and bytecode labels.

Japanese labels are about half as wide as their English translations, so the menus need help:
  TEXT    wording for one widget, where its box is too small for the shared translation
  DATA    shorter names for data rows whose narrowest box can't hold the full translation
  INTS    in-place font size / letter spacing edits (4-byte IntProperty values)
  TITLES  screen titles: letter spacing is lowered per screen until the title fits its frame
  WRAP    multi-line data re-wrapped to the width of the box that shows it
  BYTES   same-size string patches inside Blueprint bytecode (labels built in script)

Widths come from ghg.fontmetrics, fitted against in-game screenshots (within about 1%).
Box sizes come from the widget layouts in the game assets.
"""
import fnmatch
import os
import re

from .common import WORK
from .fontmetrics import Font

W = 'gohellgo/Content/Anzu/WBP/'
VN = 'gohellgo/Plugins/VN_Plugin/Content/VN_Plus/BluePrint/Widget/'
MAKINAS = os.path.join(WORK, 'fonts', 'Makinas-4-Square.ufont')

ITEM_SLOT = W + '60_Shop/WBP_Parts_Cmn_Slot/WBP_Item_Slot'
BATTLE_ITEM_SLOT = W + '51_54_Battle/HUD_Btl_Slot/WBP_Pars_Btl_Slot/WBP_Btl_Item_Slot_1'
PASSIVE = W + '31_Comp_Party/WBP_Parts_L_Prof/WBP_Prof_03_1_Passive'
DUNG_TITLE = W + '50_Dung/WBP_Parts_Dung/WBP_Dung_Title'

# (asset path under WBP/ (glob), field (glob), Japanese) -> English. Wins over tm/other.json.
TEXT = [
    # small buttons (Makinas 24, 232 px): the English sub-label under each one already says the rest
    ('30_Comp_Main/WBP_Comp_Main', 'Btn_Cmn_Text_S_Main', '従業員管理', 'Staff'),
    ('50_Dung/WBP_DungeonInternal', 'Btn_Cmn_Text_S_Main', '従業員管理', 'Staff'),
    ('30_Comp_Main/WBP_Comp_Main', 'Btn_Cmn_Text_S_Main', '亡者管理', 'Souls'),
    ('21_Mng_Main/WBP_Mng_Main', 'Btn_Cmn_Text_S_Main', '会社事務所', 'Office'),
    ('41_Dead_Party/WBP_Dead_*', 'Btn_Cmn_Text_S_Main', '従業員に戻す', 'Reinstate'),
    # large buttons (Makinas 27, 262 px)
    ('00_Config/WBP_Config_Main', 'Btn_Cmn_Text_L_Main', 'タイトル画面へ', 'To Title'),
    ('21_Mng_Main/WBP_Mng_Main', 'Btn_Cmn_Text_L_Main', '業務終了', 'Clock Out'),
    ('24_Info_Dung/WBP_Info_Dung_Main', 'Btn_Cmn_Text_L_Main', '清掃業務へ', 'Go Clean Up'),
    ('22_Hell/WBP_Hell_Main', 'Btn_Cmn_Text_L_Main', '地獄から戻す', 'Bring Back'),
    # screen titles (Makinas 44): "Staff" as in the game's own English sub-titles (STAFF MANAGEMENT)
    ('31_Comp_Party/WBP_Comp_Party_Main', 'Title_M0?_Text_Main', '従業員管理', 'Manage Staff'),
    ('31_Comp_Party/WBP_Comp_Party_Sub', 'Title_M0?_Text_Main', '従業員情報', 'Staff Info'),
    ('41_Dead_Party/WBP_Dead_Main', 'Title_M0?_Text_Main', '亡者管理', 'Manage Souls'),
    ('30_Comp_Main/WBP_Comp_Main', 'Title_L0?_Text_Main', '会社事務所', 'Office'),
]

# Shorter names, replaced in every English string (dialogue included) so the game stays consistent.
# Each was too wide for the narrowest box that shows it: battle item list, passive panel, area header.
RENAMES = {
    'Industrial Deodorizer': 'Bulk Deodorizer',      # 業務用 = commercial-size
    'Industrial Softener': 'Bulk Softener',
    'Industrial Cleanser': 'Bulk Cleanser',
    'Unexpected Behavior': 'Unexpected Move',        # 想定外動作
    'Haunted Housing Complex': 'Haunted Complex',    # おばけ団地
    'Rokudo Crossroads': 'Rokudo Crossing',          # 六道辻
    'Purification Route': 'Purification Path',       # 浄化途
}

# category -> {Japanese: English}. Wins over tm/other.json everywhere the string is used.
DATA = {
    'ui': {'処分': 'Dispose',          # trash-a-soul button; "disposed of" was a sentence fragment
           '所持': 'Qty',              # owned-count tag: an 80 px black plate
           '属性': 'ATTR',             # stat column label beside HP MP VP ATK TEC SPD DEF
           'で解放': ' needed'},       # follows "LLv.2" in its own text block: "LLv.2 needed"
}

# (asset, export, property path, value): 4-byte in-place edits
INTS = [
    # VN message box and backlog: Japanese-style 0.2 em tracking makes English sprawl
    (VN + 'Text/W_TextWidget1', 'MainTextBlock', ['Font', 'LetterSpacing'], 0),
    (VN + 'BackLog/W_BackLog_EntryItem', 'ScenarioScript', ['Font', 'LetterSpacing'], 0),
    # the VN plugin hard-breaks message rows after this many characters (37, mid-word); rows are
    # word-wrapped by ghg.build, so the limit only has to stay above them
    (VN + 'Text/W_Text_Window_Object', 'Default__W_Text_Window_Object_C', ['Text Row Count'], 60),
    # item list (menu and shop): name starts at x=302, the "Qty x1" tag at x=680
    (ITEM_SLOT, 'Item_Name', ['Font', 'Size'], 20),
    (ITEM_SLOT, 'Item_Name', ['Font', 'LetterSpacing'], 0),
    # battle item list: the name has the room of the longest Japanese name (284 px)
    (BATTLE_ITEM_SLOT, 'Item_Name', ['Font', 'Size'], 18),
    (BATTLE_ITEM_SLOT, 'Item_Name', ['Font', 'LetterSpacing'], 0),
    # Hell Passive panel (320 x 120): three description lines instead of two
    (PASSIVE, 'Skill_Description', ['Font', 'Size'], 14),
    (PASSIVE, 'Skill_Name_02', ['Font', 'Size'], 20),
    # work-area header: name and description share one 832 px bar
    *[(DUNG_TITLE, t, ['Font', p], v) for t in ('Title_L01_GR', 'Title_L02_BL', 'Title_L03_RD')
      for p, v in (('Size', 28), ('LetterSpacing', 0))],
    (DUNG_TITLE, 'DungeonInfoText', ['Font', 'Size'], 14),
]

# Screen-title widgets: (class of the title instance, font size, room for the text in px)
TITLE_WIDGETS = {'WBP_Cmn_Title_M_C': (44, 555), 'WBP_Cmn_Title_L_Day_C': (44, 520)}

# Same-size patches in Blueprint bytecode: (asset, old bytes, new bytes)
BYTES = [
    # Passive lock label: Concat("LLv.", level, "で解放"). EX_UnicodeStringConst (9 bytes) becomes
    # EX_StringConst " needed" (9 bytes), so no jump offset in the function moves.
    (PASSIVE, b'\x34' + 'で解放'.encode('utf-16-le') + b'\0\0', b'\x1f needed\0'),
]

PASSIVE_DESC = ('data:DT_HellPassiveMaster.Description', 14, 306, 3)
DUNG_BAR = 694            # room for name + description in the work-area header (x 151 .. 845)
DUNG_NAME = (28, 0)
DUNG_DESC = (14, 3)


_font = None


def font():
    global _font
    if _font is None:
        _font = Font(MAKINAS)
    return _font


def text_override(rec):
    asset = rec['asset'][len(W):] if rec['asset'].startswith(W) else rec['asset']
    for a, field, ja, en in TEXT:
        if rec['ja'] == ja and fnmatch.fnmatch(asset, a) and fnmatch.fnmatch(rec['field'], field):
            return en
    return DATA.get(rec['category'], {}).get(rec['ja'])


def rename(en):
    for old, new in RENAMES.items():
        if old in en:
            en = en.replace(old, new)
    return en


def wrap(text, size, max_px, max_lines):
    """Lines of text that fit max_px at size. Keeps the original line breaks when it can."""
    f = font()

    def fill(words):
        out, cur = [], ''
        for w in words:
            cand = w if not cur else cur + ' ' + w
            if cur and f.width_px(cand, size) > max_px:
                out.append(cur)
                cur = w
            else:
                cur = cand
        return out + ([cur] if cur else [])

    paras = [p.strip() for p in re.split(r'\\n|\n', text) if p.strip()]
    lines = [ln for p in paras for ln in fill(p.split(' '))]
    if len(lines) > max_lines:
        # run the lines together; a line that ends a sentence before a capitalised one gets a period
        joined = paras[0]
        for p in paras[1:]:
            end = '.' if p[:1].isupper() and not joined.endswith(('.', '!', '?', '…', ',', ';', ':', '—')) else ''
            joined += end + ' ' + p
        lines = fill(joined.split(' '))
    return lines


def rewrap(rec, en, dung_names):
    """Re-wrapped English for data shown in a narrow multi-line box, else None."""
    cat = rec['category']
    if cat == PASSIVE_DESC[0]:
        _, size, width, n = PASSIVE_DESC
        return '\n'.join(wrap(en, size, width, n))
    if cat == 'data:DT_DungeonMaster.Description':
        name = dung_names.get(rec['path'].split('.')[0])
        if name:
            room = DUNG_BAR - font().width_px(name, *DUNG_NAME) - 16
            return '\n'.join(wrap(en, DUNG_DESC[0], room, DUNG_DESC[1]))
    return None


def title_spacing(text, size, room, current):
    """Largest letter spacing (multiple of 50, not above current) at which text fits room px."""
    f = font()
    ls = current
    while ls > 0 and f.width_px(text, size, ls) + 12 > room:
        ls -= 50
    return max(ls, 0)


def report(english, recs):
    """Overflow check of the boxes fitted here. english(rec) -> final English. Returns warnings."""
    f = font()
    out, seen = [], set()

    def check(where, text, size, ls, room, max_lines=None):
        lines = [ln for ln in re.split(r'\\n|\n', text)]
        if max_lines and len(lines) > max_lines:
            out.append(f'{where}: "{text}" needs {len(lines)} lines, room for {max_lines}')
        for line in lines:
            w = f.width_px(line, size, ls)
            if w > room:
                out.append(f'{where}: "{line}" is {w:.0f} px, room {room}')

    boxes = {
        'Btn_Cmn_Text_S_Main': ('small button', 24, 0, 232),
        'Btn_Cmn_Text_L_Main': ('large button', 27, 0, 262),
        'data:DT_ItemMaster.Name': ('item list', 20, 0, 368),
        'data:DT_HellPassiveMaster.Name': ('passive name', 20, -10, 300),
    }
    dung = {}
    for r in recs:
        en = english(r) if not r['category'].startswith('keep') and r['category'] != 'dialogue' else None
        if not en:
            continue
        box = boxes.get(r['field']) or boxes.get(r['category'])
        if box and (box[0], en) not in seen:
            seen.add((box[0], en))
            check(*box[:1], en, *box[1:])
        if r['category'] == PASSIVE_DESC[0] and (PASSIVE_DESC[0], en) not in seen:
            seen.add((PASSIVE_DESC[0], en))
            check('passive description', rewrap(r, en, {}), PASSIVE_DESC[1], 0, PASSIVE_DESC[2], PASSIVE_DESC[3])
        if r['category'].startswith('data:DT_DungeonMaster.') and int(r['path'].split('/')[1].split('.')[0]) >= 10000:
            dung.setdefault(r['path'].split('.')[0], {})[r['field']] = (r, en)
    names = {row: v['Name'][1] for row, v in dung.items() if 'Name' in v}
    for row, v in dung.items():
        if 'Name' in v and 'Description' in v:
            r, en = v['Description']
            name = v['Name'][1]
            room = DUNG_BAR - f.width_px(name, *DUNG_NAME) - 16
            check(f'area header ({name})', rewrap(r, en, names), DUNG_DESC[0], 0, room, DUNG_DESC[1])
    return out
