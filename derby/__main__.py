"""Entry point: python -m derby"""
from __future__ import annotations

import sys

from derby.app import main

if __name__ == "__main__":
    sys.exit(main())
