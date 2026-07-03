#!/usr/bin/env python3
"""Run pytest with ROS launch paths excluded from sys.path."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path = [p for p in sys.path if "ros" not in p]
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))

import pytest

args = sys.argv[1:] or ["tests/"]
sys.exit(pytest.main(args))