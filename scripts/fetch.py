#!/usr/bin/env python3
"""Run one fetch cycle, then rebuild out/.   python3 scripts/fetch.py [--only bot,banks] [--no-build]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import pipeline  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--only", help="comma list of: bot, midmarket, banks")
ap.add_argument("--no-build", action="store_true")
a = ap.parse_args()
res = pipeline.run(a.only.split(",") if a.only else None)
for k, v in res.items():
    print(f"{'OK ' if v.get('ok') else 'FAIL'} {k:10} " + (
        f"data_date={v.get('data_date')} rows={v.get('rows')} written={v.get('written')} "
        f"rejected={v.get('rejected')} anomalies={v.get('anomalies')}" if v.get("ok") else v.get("error")))
if not a.no_build:
    from tzs import build
    build.build_all()
