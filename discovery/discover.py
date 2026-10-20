#!/usr/bin/env python3
"""Phase 1 source discovery for the TZS exchange-rate tracker.

Fetches every candidate source, prints a one-line verdict plus a sample, and
saves the raw responses under discovery/samples/ so results can be inspected.
Run:  python3 discovery/discover.py        (from tzs-tracker/)
Needs: pip install -r requirements.txt     (lxml, pdfplumber)
"""
import json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from lxml import html as LH

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
os.makedirs(SAMPLES, exist_ok=True)
RESULTS = []


def curl(url, out=None, post=None, jar=None, referer=None, timeout=30):
    cmd = ["curl", "-sS", "-L", "-A", UA, "-m", str(timeout), "-w", "\n%{http_code}|%{content_type}"]
    if jar:
        cmd += ["-b", jar, "-c", jar]
    if referer:
        cmd += ["-e", referer]
    for k, v in (post or {}).items():
        cmd += ["--data-urlencode", f"{k}={v}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True)
    body, _, tail = p.stdout.rpartition(b"\n")
    code, _, ctype = tail.decode(errors="replace").partition("|")
    if out:
        with open(os.path.join(SAMPLES, out), "wb") as f:
            f.write(body)
    return int(code or 0), ctype, body


def report(name, ok, detail, sample=""):
    RESULTS.append((name, ok))
    print(f"\n[{'OK ' if ok else 'NO '}] {name}\n     {detail}")
    if sample:
        print("     sample:", sample)


def num(s):
    return float(re.sub(r"[\s,]", "", s).replace(",", "."))


def rows_of(table):
    return [[re.sub(r"\s+", " ", (c.text_content() or "")).strip() for c in r.xpath("./th|./td")] for r in table.xpath(".//tr")]


def bot_live():
    code, _, b = curl("https://www.bot.go.tz/ExchangeRate/excRates", "bot_live.html")
    t = LH.fromstring(b.decode("utf-8", "replace"))
    rows = [r for r in rows_of(t.xpath('//table[@id="table1"]')[0]) if len(r) >= 6 and r[0].isdigit()]
    usd = next(r for r in rows if r[1] == "USD")
    report("BoT indicative rates (live table)", code == 200 and len(rows) > 30,
           f"HTTP {code}; plain server-rendered HTML, no bot protection; {len(rows)} currencies; trade date {usd[5]}",
           f"USD buy {usd[2]} sell {usd[3]} mean {usd[4]}")


def bot_history():
    jar = tempfile.mktemp()
    url = "https://www.bot.go.tz/ExchangeRate/previous_rates"
    _, _, page = curl(url, jar=jar)
    tok = re.search(rb'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page).group(1).decode()
    res = {}
    for label, a, b in (("recent", "10/12/2026", "10/20/2026"), ("2000", "01/01/2000", "01/07/2000"), ("1996", "01/01/1996", "01/07/1996")):
        time.sleep(2)
        _, _, body = curl(url, f"bot_hist_{label}.html", post={"__RequestVerificationToken": tok, "dateFrom": a, "dateTo": b}, jar=jar, referer=url)
        t = LH.fromstring(body.decode("utf-8", "replace"))
        rows = [r for tb in t.xpath("//table") for r in rows_of(tb) if len(r) >= 5 and r[0].isdigit()]
        res[label] = rows
    os.path.exists(jar) and os.remove(jar)
    usd = [r for r in res["recent"] if r[1] == "USD"]
    future = [r[5] for r in usd if datetime.strptime(r[5], "%d-%b-%y").date() > datetime.now(timezone.utc).date()]
    report("BoT history (POST form, mm/dd/yyyy)", bool(res["2000"]),
           f"works; earliest found 2000 ({len(res['2000'])} rows), nothing in 1996 ({len(res['1996'])} rows). "
           f"WARNING: table forward-fills weekends/holidays and future dates ({future}) - not real observations",
           "; ".join(f"{r[5]} {r[4]}" for r in usd[:4]))


def fx_apis():
    code, _, b = curl("https://open.er-api.com/v6/latest/USD", "erapi.json")
    d = json.loads(b)
    report("open.er-api.com", d.get("result") == "success" and "TZS" in d["rates"],
           f"HTTP {code}; no key; CORS open; updates ONCE A DAY ({d['time_last_update_utc']}); attribution required; no free history",
           f"USD/TZS {d['rates']['TZS']}")
    code, _, b = curl("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json", "fawaz.json")
    d = json.loads(b)
    code2, _, _ = curl("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@2024-03-02/v1/currencies/usd.json")
    code3, _, _ = curl("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@2024-03-01/v1/currencies/usd.json")
    report("fawazahmed0 currency-api (jsDelivr)", "tzs" in d["usd"],
           f"HTTP {code}; no key; CORS open; DAILY; dated history from 2024-03-02 ({code2}); 2024-03-01 -> {code3}; has a pages.dev mirror",
           f"{d['date']} USD/TZS {d['usd']['tzs']}")
    code, _, b = curl("https://www.floatrates.com/daily/usd.json", "floatrates.json")
    d = json.loads(b)["tzs"]
    report("FloatRates", True, f"HTTP {code}; no key; refreshed a few times a day; no history; terms NOT found on site - verify", f"USD/TZS {d['rate']} @ {d['date']}")
    code, _, b = curl("https://api.frankfurter.app/currencies", "frankfurter.json")
    report("frankfurter.app (ECB)", False, f"HTTP {code}; TZS not supported ({'TZS' in json.loads(b)})")
    code, _, b = curl("https://api.exchangerate.host/live?access_key=x&currencies=TZS", "exh.json")
    report("exchangerate.host", False, f"key required now: {json.loads(b).get('error', {}).get('type')}")
    code, _, b = curl("https://allratestoday.com/api/v1/central-bank/botz/latest", "art.json")
    report("AllRatesToday BoT mirror (spec's fallback)", False, f"HTTP {code}: API key required ({b.decode()[:70]})")


def crdb():
    code, _, b = curl("https://crdbbank.co.tz/en/forex", "crdb.html")
    h = b.decode("utf-8", "replace")
    t = LH.fromstring(h)
    rows = [r for r in rows_of(t.xpath("//table")[0]) if len(r) == 4 and r[1].isalpha()]
    usd = next(r for r in rows if r[1] == "USD")
    stamp = re.search(r"Last Updated:\s*([A-Za-z]{3} \d{1,2}, \d{4}, \d{2}:\d{2})", re.sub(r"<[^>]+>", " ", h))
    report("CRDB", code == 200 and bool(usd), f"HTTP {code}; server-rendered table behind Cloudflare but not challenged; {len(rows)} currencies; page stamp: {stamp.group(1) if stamp else None} (EAT); 'indicative only'",
           f"USD buy {usd[2]} sell {usd[3]}")


def pdf_rows(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return pdf.pages[0].extract_text() or "", pdf.pages[0].extract_tables(), pdf.metadata


def nbc():
    code, ctype, _ = curl("https://www.nbc.co.tz/en/feeds/exchange-rates/", "nbc.pdf")
    text, tables, meta = pdf_rows(os.path.join(SAMPLES, "nbc.pdf"))
    usd = next(r for tb in tables for r in tb if r and r[1:2] == ["USD"])
    report("NBC (PDF feed)", code == 200 and "pdf" in ctype,
           f"HTTP {code}; PDF, stable URL under /feeds/ (robots.txt only blocks /content/dam/); header: '{text.splitlines()[2]} / {text.splitlines()[3]} / {text.splitlines()[4]}'",
           f"USD T.T. sell {usd[2]} T.T. buy {usd[4]} cash buy {usd[7]} cash sell {usd[8]} (decimal comma, space thousands)")


def stanbic():
    code, ctype, _ = curl("https://globalmarketsforms.stanbicbank.co.tz/gmforms/documents/clientExchangeRates.pdf", "stanbic.pdf")
    text, tables, meta = pdf_rows(os.path.join(SAMPLES, "stanbic.pdf"))
    asat = re.search(r"Indicative rates as at ([A-Za-z]+ \d{1,2}, \d{4})", text)
    usd = next(r for tb in tables for r in tb if r and r[0] == "USD")
    report("Stanbic (PDF)", code == 200 and "pdf" in ctype,
           f"HTTP {code}; PDF refreshed daily; stamp: {asat.group(1) if asat else None}; digits are split by spaces in some cells ('2 0.99' = 20.99) so collapse whitespace per cell",
           f"USD buy {usd[1]} sell {usd[2]}")


def blocked():
    code, _, b = curl("https://www.nmbbank.co.tz/", "nmb.html")
    report("NMB", False, f"HTTP {code}; Cloudflare managed challenge ('Just a moment...'); skipped per spec - not attempting to bypass")
    code, _, _ = curl("https://www.eximbank.co.tz/en/personal/treasury/fx", "exim.html")
    report("Exim", False, f"HTTP {code}; Next.js site, FX page has no rate table ('visit a branch'); other URLs are soft-404 shells")
    report("IFEM interbank rate", False, "only in BoT monthly review PDFs (monthly average); no daily parseable page found")


if __name__ == "__main__":
    for fn in (bot_live, bot_history, fx_apis, crdb, nbc, stanbic, blocked):
        try:
            fn()
        except Exception as e:  # discovery must keep going
            report(fn.__name__, False, f"script error: {type(e).__name__}: {e}")
    ok = sum(1 for _, v in RESULTS if v)
    print(f"\n{ok}/{len(RESULTS)} checks usable. Raw samples saved in {SAMPLES}")
