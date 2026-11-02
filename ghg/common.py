"""Shared paths and helpers."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'work')
# The installed game (read-only). Set GHG_GAME to use another copy.
GAME = os.environ.get('GHG_GAME') or os.path.expanduser(
    '~/Library/Application Support/CrossOver/Bottles/VisualNovels/drive_c/GoGoHellGo')
BASE_PAK = os.path.join(GAME, 'gohellgo/Content/Paks/gohellgo-WindowsNoEditor.pak')
PATCH_NAME = 'gohellgo-English_P.pak'

JP = re.compile(r'[぀-ヿ㐀-鿿！-～　-〿]')
GUID_SUFFIX = re.compile(r'_\d+_[0-9A-F]{32}')


def has_jp(text):
    return bool(text) and bool(JP.search(text))


def field_name(path):
    """Last property name in a path, without the blueprint GUID suffix or array index."""
    return re.sub(r'\[\d+\]|\{.*\}', '', GUID_SUFFIX.sub('', path.split('.')[-1]))
