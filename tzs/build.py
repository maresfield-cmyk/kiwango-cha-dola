"""Derive every published JSON/CSV in out/ from the history store. Deterministic: same
history in, same out/ files out (apart from generated_at)."""
import bisect
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import quality, store
from .sources import midmarket

OUT = store.OUT


# ---------- series assembly ----------------------------------------------

def _f(x):
    return None if x in (None, "") else float(x)


def bot_series():
    """{ccy: {"rows": [(date,buy,sell,mean)], "excluded": {date: reason}, "origins": {date: origin}}}
    Live non-carried observations win over backfill for the same date. Typos are excluded
    (not edited), then consecutive identical tables are collapsed to their first date."""
    obs = defaultdict(dict)
    for r in store.read_history("bot"):
        if "carried" in r["flags"]:
            continue
        k = (r["currency"], r["date"])
        cur = obs[r["currency"]].get(r["date"])
        rank = (r["origin"] == "live", r["observed_at"])
        if cur is None or rank > cur[0]:
            obs[r["currency"]][r["date"]] = (rank, (_f(r["buying"]), _f(r["selling"]), _f(r["mean"])), r["origin"])
    res = {}
    for ccy, by_d in obs.items():
        days = sorted(by_d)
        bad = quality.spikes([(d, by_d[d][1][2]) for d in days], 3, 25)
        rows, last = [], None
        for d in days:
            if d in bad:
                continue
            v = by_d[d][1]
            if v == last:
                continue
            rows.append((d,) + v)
            last = v
        res[ccy] = {"rows": rows, "excluded": bad, "origins": {d: by_d[d][2] for d in days}}
    return res


def mid_series(official_usd):
    obs = defaultdict(dict)
    for r in store.read_history(midmarket.FAWAZ):
        obs[r["currency"]][r["date"]] = _f(r["mean"])
    res = {}
    for ccy, by_d in obs.items():
        days = sorted(by_d)
        bad = quality.spikes([(d, by_d[d]) for d in days], 5, 4)
        if ccy == "USD":
            bad.update({k: v for k, v in quality.diverging(by_d, official_usd, 5).items() if k not in bad})
        res[ccy] = {"rows": [(d, by_d[d]) for d in days if d not in bad], "excluded": bad}
    return res


# ---------- calculations ---------------------------------------------------

def value_on_or_before(rows, target, idx):
    ds = [r[0] for r in rows]
    i = bisect.bisect_right(ds, target) - 1
    return (rows[i][0], rows[i][idx]) if i >= 0 else None


def changes(rows, idx):
    """1d/7d/30d/YTD/1y change of the latest value, in TZS and %."""
    if not rows:
        return {}
    ld, lv = rows[-1][0], rows[-1][idx]
    d0 = date.fromisoformat(ld)
    targets = {"d1": d0 - timedelta(days=1), "d7": d0 - timedelta(days=7), "d30": d0 - timedelta(days=30),
               "ytd": date(d0.year - 1, 12, 31), "y1": d0.replace(year=d0.year - 1) if not (d0.month == 2 and d0.day == 29) else date(d0.year - 1, 2, 28)}
    out = {}
    for k, t in targets.items():
        base = value_on_or_before(rows, t.isoformat(), idx)
        if base is None or base[0] == ld:
            out[k] = None
            continue
        out[k] = {"from_date": base[0], "from_value": base[1], "tzs": round(lv - base[1], 6),
                  "pct": round((lv / base[1] - 1) * 100, 4)}
    return out


def spread(buy, sell):
    if buy is None or sell is None:
        return None
    mid = (buy + sell) / 2
    return {"tzs": round(sell - buy, 6), "pct": round((sell - buy) / mid * 100, 4)}


def pct_vs(x, ref):
    return None if x is None or not ref else {"tzs": round(x - ref, 6), "pct": round((x / ref - 1) * 100, 4)}


def bank_latest():
    """{bank: {ccy: row}} most recent observation per currency."""
    out = {}
    for b in store.config()["banks"]:
        out[b] = store.latest_by_currency(b)
    return out


def fresh(row, now):
    obs = datetime.strptime(row["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    day = date.fromisoformat(row["date"])
    return (now - obs) < timedelta(hours=36) and (now.date() - day).days <= 3


def best_banks(banks, ccy, now):
    live = {b: r[ccy] for b, r in banks.items() if ccy in r and fresh(r[ccy], now)}
    if not live:
        return None
    hi = max(float(r["buying"]) for r in live.values())
    lo = min(float(r["selling"]) for r in live.values())
    return {"sell_foreign_best_buying": {"rate": hi, "banks": sorted(b for b, r in live.items() if float(r["buying"]) == hi)},
            "buy_foreign_best_selling": {"rate": lo, "banks": sorted(b for b, r in live.items() if float(r["selling"]) == lo)},
            "compared": sorted(live)}


# ---------- outputs --------------------------------------------------------

def _rows_json(fields, rows):
    return {"fields": fields, "rows": [list(r) for r in rows]}


def build_all(verbose=True):
    cfg = store.config()
    now = datetime.now(timezone.utc)
    hub = cfg["hub_currencies"]
    bots = bot_series()
    official_usd = {r[0]: r[3] for r in bots["USD"]["rows"]}
    mids = mid_series(official_usd)
    banks = bank_latest()
    sp = store.DATA / "status.json"
    status = json.loads(sp.read_text()) if sp.exists() else {}

    latest = {"generated_at": store.now_iso(), "currencies": {}, "status": status.get("sources", {})}
    quality_report = {"bot": {}, "midmarket": {}}
    bot_today = store.latest_by_currency("bot")  # raw latest observation (may be carried)
    for ccy in hub:
        entry = {}
        rows = bots.get(ccy, {}).get("rows", [])
        if rows:
            d, b, s, m = rows[-1]
            carried_row = bot_today.get(ccy)
            entry["bot"] = {"date": d, "buying": b, "selling": s, "mean": m, "spread": spread(b, s),
                            "change": changes(rows, 3),
                            "checked_at": carried_row["observed_at"] if carried_row else None,
                            "new_publication_today": bool(carried_row and "carried" not in carried_row["flags"] and carried_row["date"] == d)}
        mrows = mids.get(ccy, {}).get("rows", [])
        if mrows:
            md, mv = mrows[-1]
            entry["mid_market"] = {"date": md, "rate": mv, "source": midmarket.FAWAZ,
                                   "change": changes(mrows, 1),
                                   "vs_official_mean": pct_vs(mv, entry.get("bot", {}).get("mean"))}
        bb = {}
        for b, rs in banks.items():
            r = rs.get(ccy)
            if r:
                buy, sell = float(r["buying"]), float(r["selling"])
                ref = entry.get("bot", {}).get("mean")
                bb[b] = {"date": r["date"], "observed_at": r["observed_at"], "published_at": r["published_at"] or None,
                         "buying": buy, "selling": sell, "spread": spread(buy, sell),
                         "buying_vs_official_mean": pct_vs(buy, ref), "selling_vs_official_mean": pct_vs(sell, ref),
                         "flags": r["flags"] or None, "fresh": fresh(r, now)}
        if bb:
            entry["banks"] = bb
            entry["best_banks"] = best_banks(banks, ccy, now)
        latest["currencies"][ccy] = entry
    latest["bank_names"] = cfg["bank_names"]
    store.write_json(OUT / "latest.json", latest)

    # series files (hub currencies only; full BoT table is in history CSVs)
    for ccy in hub:
        c = ccy.lower()
        rows = bots.get(ccy, {}).get("rows", [])
        store.write_json(OUT / "series" / f"bot-{c}.json", {"currency": ccy, "source": "Bank of Tanzania",
                         **_rows_json(["date", "buying", "selling", "mean"], rows)})
        if rows:
            last = date.fromisoformat(rows[-1][0])
            for tag, days in (("30d", 30), ("1y", 365)):
                cut = (last - timedelta(days=days)).isoformat()
                # a window must start with the value in effect at its left edge
                base = value_on_or_before(rows, cut, 3)
                win = [r for r in rows if r[0] >= cut]
                if base and (not win or win[0][0] != cut):
                    seed = [r for r in rows if r[0] == base[0]]
                    win = seed + win
                store.write_json(OUT / "series" / f"bot-{c}-{tag}.json", {"currency": ccy, **_rows_json(["date", "buying", "selling", "mean"], win)})
            monthly = defaultdict(list)
            for r in rows:
                monthly[r[0][:7]].append(r[3])
            store.write_json(OUT / "series" / f"bot-{c}-monthly.json", {"currency": ccy, **_rows_json(
                ["month", "mean_of_means"], [(k, round(sum(v) / len(v), 4)) for k, v in sorted(monthly.items())])})
        mrows = mids.get(ccy, {}).get("rows", [])
        if mrows:
            store.write_json(OUT / "series" / f"mid-{c}.json", {"currency": ccy, "source": midmarket.FAWAZ, **_rows_json(["date", "rate"], mrows)})
        quality_report["bot"][ccy] = bots.get(ccy, {}).get("excluded", {})
        quality_report["midmarket"][ccy] = mids.get(ccy, {}).get("excluded", {})

    # mid-market vs official, USD, daily
    od = sorted(official_usd)
    gap = []
    for d, v in mids.get("USD", {}).get("rows", []):
        i = bisect.bisect_right(od, d) - 1
        if i >= 0:
            o = official_usd[od[i]]
            gap.append((d, v, o, round(v - o, 4), round((v / o - 1) * 100, 4)))
    store.write_json(OUT / "series" / "mid-vs-official-usd.json", _rows_json(["date", "mid_market", "official_mean", "gap_tzs", "gap_pct"], gap))

    # monthly CSV for /historia/
    months = sorted({r[0][:7] for c in hub for r in bots.get(c, {}).get("rows", [])})
    avg = {c: defaultdict(list) for c in hub}
    for c in hub:
        for r in bots.get(c, {}).get("rows", []):
            avg[c][r[0][:7]].append(r[3])
    (OUT / "csv").mkdir(parents=True, exist_ok=True)
    with open(OUT / "csv" / "bot-monthly-mean.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month"] + hub)
        for m in months:
            w.writerow([m] + [round(sum(avg[c][m]) / len(avg[c][m]), 4) if avg[c].get(m) else "" for c in hub])

    store.write_json(OUT / "quality.json", {"generated_at": store.now_iso(), **quality_report})
    store.write_json(OUT / "reconcile.json", reconcile())
    if verbose:
        n = sum(len(v) for v in quality_report["bot"].values()) + sum(len(v) for v in quality_report["midmarket"].values())
        print(f"built out/: {len(hub)} currencies, {n} points excluded as source errors, latest BoT USD "
              f"{latest['currencies']['USD']['bot']['date']}")


def reconcile():
    """Where the live table and the history table disagree, and the date offset between them."""
    live, back = defaultdict(dict), defaultdict(dict)
    for r in store.read_history("bot"):
        if r["currency"] != "USD" or "carried" in r["flags"]:
            continue
        (live if r["origin"] == "live" else back)[r["date"]] = _f(r["mean"])
    items = []
    for d in sorted(live):
        match = sorted(bd for bd, v in back.items() if v == live[d])
        items.append({"live_date": d, "live_mean": live[d], "backfill_value_same_date": back.get(d),
                      "backfill_dates_with_identical_value": match,
                      "offset_days": [(date.fromisoformat(m) - date.fromisoformat(d)).days for m in match]})
    return {"generated_at": store.now_iso(), "usd": items,
            "note": "offset_days of +1 would confirm BoT's history labels a rate one day after its live trade date"}
