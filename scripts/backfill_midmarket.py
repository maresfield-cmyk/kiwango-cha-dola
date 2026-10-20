#!/usr/bin/env python3
"""Backfill the mid-market series from fawazahmed0's dated daily snapshots (free, from 2024-03-02).
Raw snapshots are cached and never re-fetched.   python3 scripts/backfill_midmarket.py"""
import concurrent.futures as cf
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import store  # noqa: E402
from tzs.sources import midmarket  # noqa: E402

start = dt.date.fromisoformat(store.config()["midmarket"]["backfill_from"])
end = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
have = {r["date"] for r in store.read_history(midmarket.FAWAZ)}
todo = [d for d in (start + dt.timedelta(n) for n in range((end - start).days + 1)) if d.isoformat() not in have]
print(f"{len(todo)} days to fetch ({start}..{end}), {len(have)} already stored")


def one(d):
    ds = d.isoformat()
    parts = [midmarket.FAWAZ, ds + ".json"]
    try:
        if store.raw_path(parts).exists():
            content = store.read_raw(parts)
            return ds, midmarket.parse_fawaz(content, midmarket.fawaz_urls(ds)[0], "backfill", store.now_iso()), None
        return ds, midmarket.fetch_fawaz(ds, origin="backfill"), None
    except Exception as e:
        return ds, None, f"{type(e).__name__}: {e}"


rows, missing = [], []
with cf.ThreadPoolExecutor(6) as ex:
    for ds, r, err in ex.map(one, todo):
        if r:
            rows.extend(r)
        else:
            missing.append((ds, err))
n = store.append_history(midmarket.FAWAZ, rows)
print(f"rows written: {n}; days with no snapshot: {len(missing)}")
for ds, err in missing[:8]:
    print("  missing", ds, err)
store.write_json(store.DATA / "reports" / "midmarket_backfill.json", {"generated_at": store.now_iso(), "missing": missing})
