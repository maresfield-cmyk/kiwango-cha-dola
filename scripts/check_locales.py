#!/usr/bin/env python3
"""Build the site and report locale keys that are missing, unused, or identical to English (untranslated)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import site, store  # noqa: E402

b = site.Builder(preview=True)
used = b.build()
en = json.load(open(store.ROOT / "locales" / "en.json"))
sw = json.load(open(store.ROOT / "locales" / "sw.json"))
meta = lambda k: k.startswith("_")
all_used = set().union(*used.values())
print("missing in sw:", sorted(k for k in en if k not in sw and not meta(k)))
print("missing in en:", sorted(k for k in sw if k not in en and not meta(k)))
print("unused in en :", sorted(k for k in en if k not in all_used and not meta(k)))
same = [k for k in en if k in sw and en[k] == sw[k] and not meta(k) and isinstance(en[k], str) and len(en[k]) > 3]
print(f"sw strings still identical to English: {len(same)} of {len(en)} (expected until the writer's copy is imported)")
