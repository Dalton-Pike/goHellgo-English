# Contributing

Thank you for helping improve the Go Hell Go English Patch. The English text is a machine translation, so corrections from people who play the game are what make it better.

## Suggesting a translation fix

Open a **[Translation fix request](../../issues/new?template=translation-fix.yml)**. The form asks for four things, and all four are required:

| | What to write | Example (made up) |
|---|---|---|
| **Chapter** | Where the line appears. Pick it from the list. Use "Menus, items, skills or battle text" for anything outside the story. | #01 Welcome to Hell |
| **Line** | The line exactly as it reads in the game, with the speaker if there is one. Copy it letter for letter: it's how the line gets found. | Tomori: "Then I messaged Yuka-chan on LIME for a bit, and wandered around for a while~..." |
| **Change** | What it should say instead | Tomori: "Then I was on LIME with Yuka-chan for a bit, and wandered around for a while~..." |
| **Reason** | Why the change is needed | Mistranslation: ちょっとLIMEして means chatting on LIME, not one message. |

Requests missing any of these may be closed without changes.

### Tips

- **One line per request.** A few lines from the same scene are fine together.
- **A screenshot helps.** So does the original Japanese, if you can read it. Both are optional.
- **What makes a good reason:** a meaning that's wrong, a name or term that's inconsistent, the wrong tone or character voice, a typo, an honorific that was dropped, or text that runs out of its box.
- **The rules every fix must follow:**
  - Stay faithful to the Japanese.
  - Japanese names stay Japanese, in Hepburn without macrons.
  - Honorifics such as -chan and -san are kept.
  - Nothing is censored, softened or "modernized".
- **The maintainer decides** which changes go in, and checks each against the Japanese.

## Reporting a bug

For installer problems, crashes, text that runs out of its box or untranslated Japanese, open a **[Bug report](../../issues/new?template=bug-report.yml)**. Say how you run the game (Windows, CrossOver on a Mac, Wine on Linux) and which version of the patch you have.

## Code

Pull requests for the tools in `ghg/` and the installer are welcome. Start with [docs/MAINTAINING.md](docs/MAINTAINING.md). Never commit anything from `work/` or any other game files: the repository must contain no game content.

By contributing, you agree that your contribution may be used in the patch under the terms of the [LICENSE](LICENSE).
