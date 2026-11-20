"""Entry point: python -m derby (or, once frozen, Derby.exe).

`--selftest` runs derby.core.selftest instead of the normal GUI --
see that module's docstring. It is checked before anything else
imports derby.app, so a selftest run never needs a real display.
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from derby.core.selftest import main as selftest_main

        sys.exit(selftest_main())

    from derby.app import main

    sys.exit(main())
