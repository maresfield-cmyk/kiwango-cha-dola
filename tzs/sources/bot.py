"""Bank of Tanzania indicative rates: live table and the history form."""
import io
import re
from datetime import date, datetime, timedelta, timezone

from lxml import html as LH

from .. import http, store

SOURCE = "bot"
URL_LIVE = "https://www.bot.go.tz/ExchangeRate/excRates"
URL_HIST = "https://www.bot.go.tz/ExchangeRate/previous_rates"
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


class ParseError(Exception):
    pass


def _num(s):
    return float(s.replace(",", "").strip())


def _date(s):
    d, m, y = s.split("-")
    y = int(y)
    y += 1900 if y >= 90 else 2000
    return f"{y:04d}-{MONTHS[m]:02d}-{int(d):02d}"


def parse_table(content):
    """Every currency row in a BoT rates page -> list of dicts (iso dates)."""
    t = LH.fromstring(content)
    rows = []
    for tr in t.xpath("//table//tr"):
        c = [re.sub(r"\s+", " ", x.text_content() or "").strip() for x in tr.xpath("./td")]
        if len(c) >= 6 and c[0].isdigit() and re.fullmatch(r"[A-Z]{3,4}", c[1]) \
                and re.fullmatch(r"\d{1,2}-[A-Za-z]{3}-\d{2}", c[5]):
            try:
                rows.append({"currency": c[1], "buying": _num(c[2]), "selling": _num(c[3]),
                             "mean": _num(c[4]), "date": _date(c[5])})
            except (ValueError, KeyError):
                continue
    return rows


def _keep(rows):
    ex = set(store.config()["bot_exclude"])
    return [r for r in rows if r["currency"] not in ex]


def fetch_live():
    """Fetch today's table. Returns (rows as history dicts, info)."""
    content = http.fetch(URL_LIVE)
    stamp = store.now_iso()
    path = store.save_raw([SOURCE, "live", stamp[:10], stamp[11:19].replace(":", "") + "Z.html"], content)
    parsed = _keep(parse_table(content))
    if len(parsed) < 30:
        raise ParseError(f"BoT table returned {len(parsed)} rows (expected ~38): layout may have changed")
    dates = {r["date"] for r in parsed}
    if len(dates) != 1:
        raise ParseError(f"BoT table has mixed trade dates: {sorted(dates)}")
    rows = [store.row(SOURCE, r["currency"], r["date"], r["buying"], r["selling"], r["mean"],
                      observed_at=stamp, source_url=URL_LIVE, origin="live") for r in parsed]
    return rows, {"data_date": dates.pop(), "raw": path, "rows": len(rows)}


# ---- history ---------------------------------------------------------------

def history_session():
    op = http.opener(cookies=True)
    page = http.fetch(URL_HIST, op=op).decode("utf-8", "replace")
    tok = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page)
    if not tok:
        raise ParseError("BoT history form: anti-forgery token not found")
    return op, tok.group(1)


def fetch_history_range(session, d_from, d_to):
    """POST the history form. Dates are datetime.date. Returns raw bytes."""
    import urllib.parse
    op, tok = session
    body = urllib.parse.urlencode({"__RequestVerificationToken": tok,
                                   "dateFrom": d_from.strftime("%m/%d/%Y"),
                                   "dateTo": d_to.strftime("%m/%d/%Y")}).encode()
    return http.fetch(URL_HIST, data=body, op=op, headers={"Referer": URL_HIST})


def classify_days(rows, first, last):
    """Decide which dates in [first, last] carry a genuine new table.

    BoT's history table is a calendar-day series that forward-fills days with no new
    publication (Sun/Mon repeat Sat's numbers, holidays repeat the day before, and
    future dates are padded). A date is kept only if its full table differs from the
    previous date's. Weekday is deliberately NOT tested: the table's date label runs
    a day behind the publication, so a real Friday rate appears under Saturday.
    Returns (real_dates, report, by_date).
    """
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], {})[r["currency"]] = (r["buying"], r["selling"], r["mean"])
    dates = sorted(by_date)
    sig = {d: tuple(sorted(by_date[d].items())) for d in dates}
    real, carried = [], 0
    for i, d in enumerate(dates):
        if not (first <= d <= last):
            continue
        if i == 0 or sig[d] != sig[dates[i - 1]]:
            real.append(d)
        else:
            carried += 1
    return real, {"carried_dates": carried}, by_date


def mark_carried(new_rows, history_rows):
    """Flag a live table as 'carried' when BoT shows a new date but the numbers are
    identical to the previous genuine table. Mutates new_rows."""
    day = new_rows[0]["date"]
    prior = [r for r in history_rows if r["date"] < day and "carried" not in r["flags"]]
    live = [r for r in prior if r["origin"] == "live"]  # compare live-to-live: history rows can differ from live
    prior = live or prior
    same = False
    if prior:
        pd_ = max(r["date"] for r in prior)
        prev = {r["currency"]: (float(r["buying"]), float(r["selling"]), float(r["mean"]))
                for r in prior if r["date"] == pd_}
        new = {r["currency"]: (r["buying"], r["selling"], r["mean"]) for r in new_rows}
        same = prev == new
    if same:
        for r in new_rows:
            r["flags"] = ",".join(x for x in (r["flags"], "carried") if x)
    return same
