"""Paths, raw-response cache and the append-only history store."""
import csv
import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
HIST = DATA / "history"
OUT = ROOT / "out"
FIELDS = ["source", "currency", "date", "buying", "selling", "mean",
          "observed_at", "published_at", "source_url", "origin", "flags"]

_cfg = None


def config():
    global _cfg
    if _cfg is None:
        _cfg = json.loads((ROOT / "config.json").read_text())
    return _cfg


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_raw(parts, content, compress=True):
    """Write a raw response under data/raw/. Returns the repo-relative path."""
    p = RAW.joinpath(*parts)
    if compress:
        p = p.with_name(p.name + ".gz")
    p.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        with gzip.GzipFile(p, "wb", mtime=0) as f:
            f.write(content)
    else:
        p.write_bytes(content)
    return str(p.relative_to(ROOT))


def raw_path(parts):
    return RAW.joinpath(*parts[:-1]) / (parts[-1] + ".gz")


def read_raw(parts):
    with gzip.open(raw_path(parts), "rb") as f:
        return f.read()


def row(source, currency, date, buying=None, selling=None, mean=None, observed_at=None,
        published_at="", source_url="", origin="live", flags=""):
    return {"source": source, "currency": currency, "date": date, "buying": buying,
            "selling": selling, "mean": mean, "observed_at": observed_at or now_iso(),
            "published_at": published_at, "source_url": source_url, "origin": origin, "flags": flags}


def _fmt(v):
    return "" if v is None or v == "" else repr(float(v)) if not isinstance(v, str) else v


def hist_file(source, year):
    return HIST / source / f"{year}.csv"


def read_history(source, years=None):
    d = HIST / source
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.csv")):
        if years and int(f.stem) not in years:
            continue
        with open(f, newline="") as fh:
            out.extend(csv.DictReader(fh))
    return out


def _key(r):
    return (r["currency"], r["date"], _fmt(r["buying"]), _fmt(r["selling"]), _fmt(r["mean"]), r["origin"])


def append_history(source, rows):
    """Append-only: rows identical to an existing observation are skipped.
    Returns number of rows written."""
    by_year = {}
    for r in rows:
        by_year.setdefault(r["date"][:4], []).append(r)
    written = 0
    for year, rs in by_year.items():
        f = hist_file(source, year)
        f.parent.mkdir(parents=True, exist_ok=True)
        seen = set()
        exists = f.exists()
        if exists:
            with open(f, newline="") as fh:
                seen = {(x["currency"], x["date"], x["buying"], x["selling"], x["mean"], x["origin"])
                        for x in csv.DictReader(fh)}
        new = [r for r in rs if _key(r) not in seen]
        if not new:
            continue
        with open(f, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if not exists:
                w.writeheader()
            for r in new:
                w.writerow({k: (_fmt(r[k]) if k in ("buying", "selling", "mean") else r[k]) for k in FIELDS})
        written += len(new)
    return written


def _ref(r):
    if r.get("mean") not in (None, ""):
        return float(r["mean"])
    if r.get("buying") not in (None, "") and r.get("selling") not in (None, ""):
        return (float(r["buying"]) + float(r["selling"])) / 2
    return None


def latest_by_currency(source):
    """Most recent stored observation per currency (by date, then observed_at)."""
    d = HIST / source
    years = sorted(int(f.stem) for f in d.glob("*.csv")) if d.exists() else []
    best = {}
    for r in read_history(source, years[-2:]):
        c = r["currency"]
        if c not in best or (r["date"], r["observed_at"]) > (best[c]["date"], best[c]["observed_at"]):
            best[c] = r
    return best


def log_alert(kind, source, detail):
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / "alerts.jsonl", "a") as f:
        f.write(json.dumps({"at": now_iso(), "type": kind, "source": source, "detail": detail}) + "\n")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)
