"""Entry point: python -m derby (or, once frozen, Derby.exe).

`--selftest` runs derby.core.selftest instead of the normal GUI --
see that module's docstring. It is checked before anything else
imports derby.app, so a selftest run never needs a real display.

The os.add_dll_directory patch and PATH setup below run before either
branch's import, because both eventually import PySide2 -- see
derby/core/utils/win_dll_search.py's module docstring for why this
matters on Windows 7.
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from derby.core.utils.win_dll_search import ensure_win_dll_search_paths

    ensure_win_dll_search_paths()

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from derby.core.selftest import main as selftest_main

        sys.exit(selftest_main())

    from derby.app import main

    sys.exit(main())
