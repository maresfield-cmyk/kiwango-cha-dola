"""One fetch cycle: every source independently, validated, appended, status recorded."""
import json
import traceback

from . import store, validate
from .sources import banks, bot, midmarket

STATUS = store.DATA / "status.json"


def _load_status():
    try:
        return json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return {"sources": {}}


def _ingest(source, rows, info):
    """Validate against last stored values, append. Returns result dict."""
    cfg = store.config()
    prev = store.latest_by_currency(source)
    ok, rejected, anomalies = validate.validate(rows, prev, cfg["anomaly_pct"])
    for r, why in rejected:
        store.log_alert("rejected_row", source, f"{r['currency']} {r['date']}: {why}")
    for r, why in anomalies:
        store.log_alert("anomaly", source, f"{r['currency']} {r['date']}: {why}; previous value kept")
    written = store.append_history(source, ok)
    return {"rows": len(rows), "written": written, "rejected": len(rejected),
            "anomalies": len(anomalies), **info}


def run(only=None):
    only = only or ["bot", "midmarket", "banks"]
    status = _load_status()
    sources = status.setdefault("sources", {})
    jobs = []
    if "bot" in only:
        jobs.append(("bot", lambda: bot.fetch_live()))
    if "midmarket" in only:
        jobs.append(("midmarket", lambda: midmarket.fetch_latest()))
    if "banks" in only:
        for b in store.config()["banks"]:
            jobs.append((b, lambda b=b: banks.fetch_bank(b)))
    results = {}
    for name, fn in jobs:
        s = sources.setdefault(name, {})
        s["last_attempt_at"] = store.now_iso()
        try:
            out = fn()
            rows, info = out
            if name == "midmarket":  # fetch_latest returns (rows, source_used)
                src, info = info, {"used": info, "data_date": rows[0]["date"]}
            else:
                src = name
            if name == "bot":
                info["carried"] = bot.mark_carried(rows, store.read_history("bot", {int(rows[0]["date"][:4]) - 1, int(rows[0]["date"][:4])}))
            res = _ingest(src, rows, info)
            s.update({"ok": True, "last_success_at": s["last_attempt_at"], "error": None, **res})
        except Exception as e:  # a failing source must never stop the others
            s.update({"ok": False, "error": f"{type(e).__name__}: {e}"})
            store.log_alert("source_failed", name, s["error"])
            traceback.print_exc()
        results[name] = s
    status["generated_at"] = store.now_iso()
    store.write_json(STATUS, status)
    return results
