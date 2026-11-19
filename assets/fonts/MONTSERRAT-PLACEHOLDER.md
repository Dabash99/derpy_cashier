# Montserrat font files are missing — place them here by hand

This step was explicitly blocked by the project's no-networking rule
(CLAUDE.md hard constraint 1): nothing in this repo or its build/tooling
fetches fonts, or anything else, over the network. `derby/core/theme/fonts.py`
already handles their absence gracefully (falls back to Cairo for Latin/
brand text), so the app runs fine without them — but Montserrat's actual
letterforms won't appear until these are added.

## What to add

Download the **static** (not variable) weights of Montserrat from the
official Google Fonts repository (OFL-licensed) and place these four
files directly in this folder:

```
assets/fonts/Montserrat-Regular.ttf
assets/fonts/Montserrat-Medium.ttf
assets/fonts/Montserrat-SemiBold.ttf
assets/fonts/Montserrat-Bold.ttf
```

Also copy Montserrat's `OFL.txt` into this folder as `Montserrat-OFL.txt`
(do not overwrite the existing `OFL.txt`, which is Cairo's license).

Static weights only — Qt's font backend on Windows 7 does not reliably
support variable fonts.

## After adding the files

1. Delete this placeholder file.
2. Run the test suite (`.venv\Scripts\python.exe -m pytest tests/test_fonts.py`)
   — `montserrat_available()` should report `True` and
   `missing_montserrat_files()` should return an empty tuple.
3. Commit the four `.ttf` files and `Montserrat-OFL.txt` together.

No code changes are needed — `derby/core/theme/fonts.py` already looks
for exactly these file names.
