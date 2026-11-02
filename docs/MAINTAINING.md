# Maintaining the patch

**Never commit `work/`.** It holds text taken from the game, the translations and the builds. It is git-ignored. Back it up yourself: it is the only copy of the translation.

## Requirements

- Python 3.11 or newer, with Pillow and numpy.
- `makensis` (NSIS 3): `brew install makensis`.
- A full copy of the game. Set `GHG_GAME` to the game folder (the one with `gohellgo.exe`). The tools only read its files.

## Fix a line

1. Find the line:
   ```sh
   python3 -m ghg.find "the line as quoted in the request"
   ```
2. Edit the English in the file it names:
   - `work/tm/dialogue/<scene>.json` for story lines;
   - `work/tm/other.json` for everything else.

   Don't add line breaks to dialogue.
3. Rebuild with `python3 -m ghg.build`. Fix anything its overflow report lists.

If the game itself is updated, re-extract its text first with `python3 -m ghg.extract`.

## Release

1. Bump the version in the `LICENSE` header, the README and `CHANGELOG.md`.
2. Build the installer:
   ```sh
   python3 -m ghg.package --version 0.0.2-beta --url https://github.com/<owner>/<repo>
   ```
   This writes the `.exe` and its `.sha256` file to `work/dist/`.
3. Test it in a throwaway bottle or Wine prefix, never in the one you play in. Check that it:
   - finds the game when it's put in the game folder;
   - stops with nothing installed when there's no game;
   - uninstalls cleanly.
4. Create a GitHub release tagged `v<version>`:
   - Mark it as a pre-release while the version ends in `-beta`.
   - Attach the `.exe` and `.sha256` files.
   - Paste the CHANGELOG section as the release notes.
