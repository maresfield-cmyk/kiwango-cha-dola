"""Commercial bank board rates: CRDB (HTML), NBC and Stanbic (PDF)."""
import io
import re
from datetime import datetime, timedelta, timezone

from lxml import html as LH

from .. import http, store

EAT = timezone(timedelta(hours=3))
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
FULL_MONTHS = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September October November December".split())}


class ParseError(Exception):
    pass


def _n(s, comma_decimal=False):
    s = re.sub(r"\s+", "", s or "")
    if not s:
        raise ValueError("empty")
    return float(s.replace(",", ".") if comma_decimal else s.replace(",", ""))


def _utc(dt_eat):
    return dt_eat.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- CRDB ---------------------------------------------------------------

CRDB_URL = "https://crdbbank.co.tz/en/forex"


def parse_crdb(content):
    html = content.decode("utf-8", "replace")
    m = re.search(r"Last Updated:\s*([A-Za-z]{3}) (\d{1,2}), (\d{4}), (\d{2}):(\d{2})", re.sub(r"<[^>]+>", " ", html))
    if not m:
        raise ParseError("CRDB: 'Last Updated' stamp not found")
    stamp = datetime(int(m[3]), MONTHS[m[1]], int(m[2]), int(m[4]), int(m[5]), tzinfo=EAT)
    t = LH.fromstring(content)
    rows = []
    for tr in t.xpath("//table//tr"):
        c = [re.sub(r"\s+", " ", x.text_content() or "").strip() for x in tr.xpath("./td")]
        if len(c) == 4 and re.fullmatch(r"[A-Z]{3}", c[1]):
            try:
                rows.append((c[1], _n(c[2]), _n(c[3]), ""))
            except ValueError:
                continue
    # The page's "Last Updated" is the render time (it tracks the fetch time to the minute),
    # so it is used only for the local date, never recorded as a publish time.
    return rows, stamp.strftime("%Y-%m-%d"), ""


# --- NBC ----------------------------------------------------------------

NBC_URL = "https://www.nbc.co.tz/en/feeds/exchange-rates/"


def _pdf(content):
    import pdfplumber
    return pdfplumber.open(io.BytesIO(content))


def parse_nbc(content):
    """T.T. buying/selling for every currency. Cash columns are zero for most
    currencies, so T.T. is the one basis that exists for all of them."""
    with _pdf(content) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = page.extract_tables()
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if not m:
        raise ParseError("NBC: date not found in PDF header")
    day = f"{m[3]}-{m[2]}-{m[1]}"
    wef = re.search(r"W\.?E\.?F\.?\s*(\d{1,2}):(\d{2})\s*(AM|PM)", text, re.I)
    published = ""
    if wef:
        h = int(wef[1]) % 12 + (12 if wef[3].upper() == "PM" else 0)
        published = _utc(datetime(int(m[3]), int(m[2]), int(m[1]), h, int(wef[2]), tzinfo=EAT))
    rows, seen = [], set()
    for tb in tables:
        for r in tb:
            if len(r) >= 6 and r[1] and re.fullmatch(r"[A-Z]{3}", r[1].strip()):
                code = r[1].strip()
                if code in seen:  # USD appears twice (1-20 and 50-100 units): keep the first
                    continue
                try:
                    sell, buy = _n(r[2], True), _n(r[4], True)
                except ValueError:
                    continue
                seen.add(code)
                rows.append((code, buy, sell, "tt"))
    return rows, day, published


# --- Stanbic ------------------------------------------------------------

STANBIC_URL = "https://globalmarketsforms.stanbicbank.co.tz/gmforms/documents/clientExchangeRates.pdf"


def parse_stanbic(content):
    with _pdf(content) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        tables = page.extract_tables()
    m = re.search(r"Indicative rates as at ([A-Za-z]+) (\d{1,2}), (\d{4})", text)
    if not m:
        raise ParseError("Stanbic: 'Indicative rates as at' date not found")
    day = f"{m[3]}-{FULL_MONTHS[m[1]]:02d}-{int(m[2]):02d}"
    rows = []
    for tb in tables:
        for r in tb:
            # Stanbic's PDF splits digits with spaces ('2 0.99' = 20.99); _n() removes all whitespace
            if len(r) >= 3 and r[0] and re.fullmatch(r"[A-Z]{3}", r[0].strip()):
                try:
                    rows.append((r[0].strip(), _n(r[1]), _n(r[2]), ""))
                except ValueError:
                    continue
    return rows, day, ""


BANKS = {
    "crdb": (CRDB_URL, parse_crdb, ".html"),
    "nbc": (NBC_URL, parse_nbc, ".pdf"),
    "stanbic": (STANBIC_URL, parse_stanbic, ".pdf"),
}


def fetch_bank(name):
    url, parse, ext = BANKS[name]
    content = http.fetch(url)
    stamp = store.now_iso()
    path = store.save_raw([name, stamp[:10], stamp[11:19].replace(":", "") + "Z" + ext], content)
    parsed, day, published = parse(content)
    if len(parsed) < 8:
        raise ParseError(f"{name}: only {len(parsed)} rows parsed (empty table?)")
    rows = []
    for code, buy, sell, flag in parsed:
        flags = [flag] if flag else []
        if sell and (sell - buy) / sell > 0.25:
            flags.append("wide_spread")
        rows.append(store.row(name, code, day, buy, sell, None, observed_at=stamp, published_at=published,
                              source_url=url, origin="live", flags=",".join(flags)))
    return rows, {"data_date": day, "published_at": published, "raw": path, "rows": len(rows)}
