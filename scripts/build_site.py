#!/usr/bin/env python3
"""Build site/ from out/.  python3 scripts/build_site.py [--preview] [--base-path /kiwango-cha-dola] [--base-url https://...]
Run scripts/build_out.py first if out/ is stale."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import site  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--preview", action="store_true", help="noindex + robots disallow")
ap.add_argument("--base-path", default=os.environ.get("SITE_BASE_PATH", ""))
ap.add_argument("--base-url", default=os.environ.get("SITE_BASE_URL"))
a = ap.parse_args()
b = site.Builder(preview=a.preview, base_path=a.base_path, base_url=a.base_url)
used = b.build()
n = sum(1 for _ in site.SITE.rglob("index.html"))
print(f"built {n} pages into site/ (locales: {', '.join(used)}; preview={a.preview})")
