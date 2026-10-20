"""Mid-market (indicative global) rates: fawazahmed0 primary, open.er-api fallback."""
import json
from datetime import datetime, timezone

from .. import http, store

FAWAZ = "fawazahmed0"
ERAPI = "open-er-api"


class MidError(Exception):
    pass


def _to_rows(source, day, tzs_per_usd, usd_per, url, published, origin, stamp):
    """usd_per: {CODE: units of CODE per 1 USD}. Returns TZS per 1 unit rows."""
    rows = []
    for c in store.config()["hub_currencies"]:
        if c == "USD":
            v = tzs_per_usd
        elif c in usd_per and usd_per[c]:
            v = tzs_per_usd / usd_per[c]
        else:
            continue
        rows.append(store.row(source, c, day, mean=round(v, 6), observed_at=stamp,
                              published_at=published, source_url=url, origin=origin))
    if not any(r["currency"] == "USD" for r in rows):
        raise MidError(f"{source}: no USD/TZS in response")
    return rows


def fawaz_urls(version="latest"):
    if version == "latest":
        return ["https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json",
                "https://latest.currency-api.pages.dev/v1/currencies/usd.min.json"]
    return [f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{version}/v1/currencies/usd.min.json",
            f"https://{version}.currency-api.pages.dev/v1/currencies/usd.min.json"]


def parse_fawaz(content, url, origin, stamp):
    d = json.loads(content)
    usd = {k.upper(): v for k, v in d["usd"].items()}
    if "TZS" not in usd:
        raise MidError("fawazahmed0: TZS missing")
    return _to_rows(FAWAZ, d["date"], usd["TZS"], usd, url, d["date"], origin, stamp)


def fetch_fawaz(version="latest", origin="live", cache=True):
    err = None
    for url in fawaz_urls(version):
        try:
            content = http.fetch(url, retries=2)
            stamp = store.now_iso()
            rows = parse_fawaz(content, url, origin, stamp)
            if cache:
                store.save_raw([FAWAZ, rows[0]["date"] + (".json" if origin == "backfill" else f"-{stamp[11:19].replace(':', '')}Z.json")], content)
            return rows
        except (http.FetchError, MidError, ValueError, KeyError) as e:
            err = e
    raise MidError(f"fawazahmed0 failed on all mirrors: {err}")


def fetch_erapi(origin="live"):
    url = "https://open.er-api.com/v6/latest/USD"
    content = http.fetch(url)
    stamp = store.now_iso()
    d = json.loads(content)
    if d.get("result") != "success" or "TZS" not in d.get("rates", {}):
        raise MidError("open.er-api: unexpected response")
    store.save_raw([ERAPI, stamp[:10], stamp[11:19].replace(":", "") + "Z.json"], content)
    upd = datetime.strptime(d["time_last_update_utc"], "%a, %d %b %Y %H:%M:%S %z")
    day = upd.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return _to_rows(ERAPI, day, d["rates"]["TZS"], d["rates"], url,
                    upd.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), origin, stamp)


def fetch_latest():
    """Primary then fallback. Returns (rows, source_used)."""
    try:
        return fetch_fawaz(), FAWAZ
    except MidError as e:
        store.log_alert("source_failed", FAWAZ, str(e))
        return fetch_erapi(), ERAPI
