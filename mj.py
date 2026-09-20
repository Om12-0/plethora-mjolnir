#!/usr/bin/env python
"""Portable launcher so you can run `python mj.py ...` from anywhere."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mjolnir.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
