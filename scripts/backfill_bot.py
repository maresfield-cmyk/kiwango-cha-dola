#!/usr/bin/env python3
"""Backfill BoT history. Past years are fetched once and cached (never re-fetched);
the current year is refreshed each run.   python3 scripts/backfill_bot.py [--from-year 1996]"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from tzs import store  # noqa: E402
from tzs.sources import bot  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--from-year", type=int, default=store.config()["bot_backfill_from_year"])
ap.add_argument("--rebuild-only", action="store_true", help="re-derive from cached raw, no network")
a = ap.parse_args()

today = dt.datetime.now(dt.timezone.utc).date()
session = None
report = {"generated_at": store.now_iso(), "years": {}}
total = 0
for year in range(a.from_year, today.year + 1):
    parts = ["bot", "history", f"{year}.html"]
    cached = store.raw_path(parts).exists()
    last = min(dt.date(year, 12, 31), today)
    if year == today.year or not cached:
        if a.rebuild_only:
            if not cached:
                continue
        else:
            session = session or bot.history_session()
            raw = bot.fetch_history_range(session, dt.date(year - 1, 12, 20), last)
            store.save_raw(parts, raw)
            time.sleep(3)
    raw = store.read_raw(parts)
    fetched_at = dt.datetime.fromtimestamp(store.raw_path(parts).stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = bot._keep(bot.parse_table(raw))
    if not rows:
        report["years"][year] = {"rows": 0}
        print(f"{year}: no data")
        continue
    real, rep, by_date = bot.classify_days(rows, f"{year}-01-01", last.isoformat())
    out = [store.row("bot", c, d, b, s, m, observed_at=fetched_at, source_url=bot.URL_HIST, origin="backfill")
           for d in real for c, (b, s, m) in by_date[d].items()]
    written = store.append_history("bot", out)
    total += written
    report["years"][year] = {"new_tables": len(real), "carried_dates": rep["carried_dates"], "rows_written": written}
    print(f"{year}: {len(real):3} new tables, {rep['carried_dates']:3} carried-forward dates dropped; +{written} rows")
store.write_json(store.DATA / "reports" / "bot_backfill.json", report)
print("total rows written:", total)
