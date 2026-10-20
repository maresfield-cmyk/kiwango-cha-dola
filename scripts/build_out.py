#!/usr/bin/env python3
"""Rebuild out/ from stored history only (no network)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import build  # noqa: E402

build.build_all()
