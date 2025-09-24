#!/usr/bin/env python3
"""
Deprecated wrapper: please use ./test.py

This script delegates execution to test.py, forwarding all arguments.
"""

import os
import sys
from pathlib import Path


def main() -> None:
    test = Path(__file__).resolve().parent / "test.py"
    os.execv(sys.executable, [sys.executable, str(test)] + sys.argv[1:])


if __name__ == "__main__":
    main()
