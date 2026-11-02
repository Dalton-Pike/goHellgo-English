"""Find a line in the translation memory: the first step of handling a translation fix request.

  python3 -m ghg.find "text as it reads in the game"      (English or Japanese, any part of the line)
  python3 -m ghg.find --chapter 3 "text"                  (only story scenes of chapter 3)

For each match it prints the file to edit, the key inside it, the chapter, the Japanese and the current English.
Edit the English in that file, then run `python3 -m ghg.build` and `python3 -m ghg.package` (docs/MAINTAINING.md).
"""
import argparse
import glob
import json
import os
import re

from .common import WORK

QUOTES = str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'", '…': '...', '　': ' '})


def norm(text):
    return re.sub(r'\s+', ' ', (text or '').translate(QUOTES).replace('\\n', ' ')).strip().lower()


def chapter_of(scene):
    m = re.match(r'(?i)main(\d\d)', scene)
    if m:
        return f'Chapter {int(m.group(1))}'
    m = re.match(r'(?i)hell(\d\d)', scene)
    if m:
        return f'Hell scene (chapter {int(m.group(1))})'
    return 'side scene'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('text')
    ap.add_argument('--chapter', type=int)
    ap.add_argument('--tm', default=os.path.join(WORK, 'tm'))
    args = ap.parse_args()
    needle = norm(args.text)
    if len(needle) < 3:
        raise SystemExit('give at least 3 characters of the line')
    japanese = {}
    for line in open(os.path.join(WORK, 'strings.jsonl'), encoding='utf-8'):
        rec = json.loads(line)
        japanese[rec['id']] = rec['ja']

    hits = 0
    for path in sorted(glob.glob(os.path.join(args.tm, 'dialogue', '*.json'))):
        scene = os.path.basename(path)[:-5]
        chapter = chapter_of(scene)
        if args.chapter and chapter != f'Chapter {args.chapter}':
            continue
        for key, english in json.load(open(path, encoding='utf-8')).items():
            if needle in norm(english) or needle in norm(japanese.get(key)):
                hits += 1
                print(f'{os.path.relpath(path, WORK)}  [{chapter}, scene {scene}]\n  key: {key}\n'
                      f'  ja:  {japanese.get(key, "?")}\n  en:  {english}\n')
    if not args.chapter:
        other = os.path.join(args.tm, 'other.json')
        for category, table in json.load(open(other, encoding='utf-8')).items():
            for ja, english in table.items():
                if needle in norm(english) or needle in norm(ja):
                    hits += 1
                    print(f'{os.path.relpath(other, WORK)}  [{category}]\n  ja:  {ja}\n  en:  {english}\n')
    print(f'{hits} match(es)' + ('' if hits else '. Text drawn into images (title cards, icons) is in work/chapter and ghg/texture.py.'))


if __name__ == '__main__':
    main()
