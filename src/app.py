#!/usr/bin/env python3
"""
Backwards-compatibility shim — redirects to src.cli.

Use `python -m src.cli` instead.
"""

import sys
from src.cli import main

if __name__ == '__main__':
    sys.exit(main())
