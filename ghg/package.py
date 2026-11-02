"""Wrap the built patch pak into the Windows setup .exe.

Run:  python3 -m ghg.package --version 0.0.1-beta [--url https://github.com/<owner>/<repo>]
      (after python3 -m ghg.build)

Output: work/dist/GoHellGo-English-Setup-<version>.exe and a .sha256 file next to it.
--url adds a "Report a translation mistake" link to the last installer page.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess

from .common import PATCH_NAME, ROOT, WORK


def vi_version(version):
    """Windows file-version form (four numbers) of a version such as 0.0.1-beta."""
    nums = re.findall(r'\d+', version.split('-')[0])[:4]
    return '.'.join(nums + ['0'] * (4 - len(nums)))


def installer_license(out_dir):
    """LICENSE as UTF-16 with a byte-order mark and CRLF line ends: the form the installer's license page reads."""
    text = open(os.path.join(ROOT, 'LICENSE'), encoding='utf-8').read()
    path = os.path.join(out_dir, 'LICENSE-installer.txt')
    with open(path, 'wb') as f:
        f.write('﻿'.encode('utf-16-le') + text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-16-le'))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--url', help='project page, shown as a link on the last installer page')
    args = ap.parse_args()
    if not re.fullmatch(r'[0-9A-Za-z.\-]+', args.version):
        raise SystemExit('version may only use letters, digits, dots and dashes')
    if args.url and not re.fullmatch(r'https://[\w./\-]+', args.url):
        raise SystemExit('--url must be a plain https:// address')
    dist = os.path.join(WORK, 'dist')
    build = os.path.join(WORK, 'build')
    os.makedirs(build, exist_ok=True)
    manifest = json.load(open(os.path.join(dist, 'manifest.json')))
    patch = os.path.join(dist, PATCH_NAME)
    out = os.path.join(dist, f'GoHellGo-English-Setup-{args.version}.exe')
    manual = os.path.join(WORK, 'manual_html', 'en')
    cmd = ['makensis', '-V2', '-INPUTCHARSET', 'UTF8',
           f'-DPATCH_FILE={patch}', f'-DOUT_FILE={out}',
           f'-DBASE_SIZE={manifest["base_pak_size"]}', f'-DVERSION={args.version}',
           f'-DVI_VERSION={vi_version(args.version)}', f'-DLICENSE_FILE={installer_license(build)}',
           *([f'-DMANUAL_DIR={manual}'] if os.path.isdir(manual) else []),
           *([f'-DPROJECT_URL={args.url}'] if args.url else []),
           os.path.join(ROOT, 'installer', 'GoHellGoEnglish.nsi')]
    subprocess.run(cmd, check=True)
    digest = hashlib.sha256(open(out, 'rb').read()).hexdigest()
    with open(out + '.sha256', 'w') as f:
        f.write(f'{digest}  {os.path.basename(out)}\n')
    print(f'wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)')
    print(f'sha256 {digest}')


if __name__ == '__main__':
    main()
