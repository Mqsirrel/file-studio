#!/usr/bin/env python3
"""Launch Convert Wheel:  python3 run.py [files...]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from convertwheel.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
