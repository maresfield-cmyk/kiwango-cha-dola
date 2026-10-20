"""Build the static site (site/) from out/ and the locale files. Server-rendered: every number is
in the HTML, charts are inline SVG, JavaScript only enhances (converter, live mid-market refresh)."""
import csv
import json
import os
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import jinja2

from . import charts, i18n, store
from .i18n import Locale, direction

ROOT = store.ROOT
OUT = store.OUT
SITE = ROOT / "site"
NAV = [("hub", "/"), ("banks", "/benki/"), ("converter", "/kikokotoo/"), ("history", "/historia/"), ("method", "/mbinu/")]
SOURCES = [
    ("bot", "Bank of Tanzania", "https://www.bot.go.tz/ExchangeRate/excRates", "bot"),
    ("mid", "fawazahmed0 currency-api", "https://github.com/fawazahmed0/exchange-api", "midmarket"),
    ("crdb", "CRDB", "https://crdbbank.co.tz/en/forex", "crdb"),
    ("nbc", "NBC", "https://www.nbc.co.tz/en/feeds/exchange-rates/", "nbc"),
    ("stanbic", "Stanbic", "https://globalmarketsforms.stanbicbank.co.tz/gmforms/documents/clientExchangeRates.pdf", "stanbic"),
]


def _json(p):
    return json.loads((OUT / p).read_text())


class Builder:
    def __init__(self, preview=False, base_path="", base_url=None):
        self.cfg = store.config()
        self.site_cfg = self.cfg["site"]
        self.preview = preview
        self.base_path = base_path.rstrip("/")
        self.base_url = (base_url or self.site_cfg["base_url"]).rstrip("/")
        self.default = self.site_cfg["default_locale"]
        self.locales = {c: Locale(c) for c in self.site_cfg["locales"]}
        self.hub = self.cfg["hub_currencies"]
        self.banks = self.cfg["banks"]
        self.bank_names = self.cfg["bank_names"]
        self.latest = _json("latest.json")
        self.status = self.latest.get("status", {})
        self.quality = _json("quality.json")
        self.css = (ROOT / "templates" / "style.css").read_text()
        self.js_conv = (ROOT / "templates" / "conv.js").read_text()
        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True,
                                      undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
        self.env.globals["direction"] = direction
        self.env.filters["bankname"] = lambda b: self.bank_names[b]
        self.pages = []  # (locale, path) for sitemap

    # ---- helpers --------------------------------------------------------
    def prefix(self, loc):
        return "" if loc == self.default else f"/{loc}"

    def url(self, loc, path):
        """Site-relative URL (with base path). Data/API paths are not locale-prefixed."""
        if path.startswith(("/api/", "/data/")):
            return self.base_path + path
        return self.base_path + self.prefix(loc) + path

    def abs_url(self, loc, path):
        return self.base_url + self.url(loc, path)

    def series(self, name):
        return _json(f"series/{name}.json")["rows"]

    def summary(self, lc, ccy, bot):
        s = lc.t("sum.level", date=lc.date(bot["date"]), rate=lc.rate(bot["mean"]), name=lc.t(f"ccy.{ccy}"))
        for k in ("d7", "d30"):
            c = bot["change"].get(k)
            if c:
                s += " " + lc.t(f"sum.{direction(c['pct'])}", period=lc.t(f"sum.p.{k}"),
                                pct=lc.num(abs(c["pct"]), 2), name=lc.t(f"ccy.{ccy}"))
        return s

    def conv_json(self, lc):
        data = {"locale": lc.code, "bank_names": self.bank_names, "ccy": {}, "l": {
            "bot_mean": lc.t("conv.b.bot_mean"), "bot_buying": lc.t("conv.b.bot_buying"), "bot_selling": lc.t("conv.b.bot_selling"),
            "mid": lc.t("conv.b.mid"), "bot_as_of": lc.t("conv.as_of"), "checked": lc.t("conv.checked"),
            "rate_used": lc.t("conv.rate_used"), "unavailable": lc.t("conv.unavailable"),
            "buying": lc.t("tbl.buying"), "selling": lc.t("tbl.selling")}}
        for c in self.hub:
            e = self.latest["currencies"][c]
            ent = {"bot": {k: e["bot"][k] for k in ("buying", "selling", "mean")} | {"date_fmt": lc.date(e["bot"]["date"])}}
            ent["mid"] = ({"rate": e["mid_market"]["rate"], "date_fmt": lc.date(e["mid_market"]["date"])} if e.get("mid_market") else None)
            ent["banks"] = {b: {"buying": r["buying"], "selling": r["selling"], "when": lc.dt(r["observed_at"])}
                            for b, r in e.get("banks", {}).items() if r["fresh"]}
            data["ccy"][c] = ent
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def common(self, lc, page, path):
        loc = lc.code
        others = [c for c in self.locales if c != loc][0]
        olc = self.locales[others]
        return {
            "lc": lc, "t": lc.t, "css": self.css, "preview": self.preview, "page": page,
            "url": lambda p: self.url(loc, p), "nav": NAV, "bank_names": self.bank_names, "hub": self.hub,
            "banks": self.banks, "canonical": self.abs_url(loc, path), "default_url": self.abs_url(self.default, path),
            "alternates": [{"code": c, "url": self.abs_url(c, path)} for c in self.locales],
            "other_lang": {"code": others, "label": olc.raw("lang.name"), "url": self.url(others, path)},
            "main_site": self.site_cfg["main_site"], "main_site_name": self.site_cfg["main_site_name"],
            "conv_json": self.conv_json(lc), "js_conv": self.js_conv,
        }

    def write(self, loc, path, html):
        d = SITE / self.prefix(loc).lstrip("/") / path.strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
        self.pages.append((loc, path))

    def render(self, lc, page, path, template, title, description, **ctx):
        c = self.common(lc, page, path)
        c.update(ctx, title=title, description=description)
        self.write(lc.code, path, self.env.get_template(template).render(**c))

    # ---- series ---------------------------------------------------------
    def pts(self, name, idx=3, since=None):
        rows = self.series(name)
        return [(r[0], r[idx]) for r in rows if not since or r[0] >= since]

    def ccy_charts(self, lc, ccy):
        c = ccy.lower()
        e = self.latest["currencies"][ccy]
        dp = 2 if e["bot"]["mean"] >= 100 else 4
        mid_all = [(r[0], r[1]) for r in self.series(f"mid-{c}")] if (OUT / "series" / f"mid-{c}.json").exists() else []
        out = []
        for tag, kind in (("30d", "30d"), ("1y", "1y")):
            b = self.pts(f"bot-{c}-{tag}")
            overlay = [p for p in mid_all if p[0] >= b[0][0]] if b else []
            out.append((tag, charts.chart_pair(
                b, kind, lc, lc.t("chart.title", name=lc.t(f"ccy.{ccy}"), range=lc.t(f"range.{tag}")),
                lc.t("chart.desc", a=lc.num(b[0][1], dp), da=lc.date(b[0][0]), b=lc.num(b[-1][1], dp), db=lc.date(b[-1][0])) if b else "",
                series2=overlay, dp=dp), bool(overlay)))
        monthly = [(r[0] + "-01", r[1]) for r in self.series(f"bot-{c}-monthly")]
        out.append(("max", charts.chart_pair(monthly, "max", lc, lc.t("chart.title", name=lc.t(f"ccy.{ccy}"), range=lc.t("range.max")),
                                              lc.t("chart.desc", a=lc.num(monthly[0][1], dp), da=lc.month(monthly[0][0][:7]),
                                                   b=lc.num(monthly[-1][1], dp), db=lc.month(monthly[-1][0][:7])), dp=dp), False))
        return out

    # ---- pages ----------------------------------------------------------
    def build_pages(self, lc):
        L = self.latest["currencies"]
        usd = L["USD"]
        # hub
        c30 = self.ccy_charts(lc, "USD")[0]
        self.render(lc, "hub", "/", "hub.html", lc.t("hub.title"), lc.t("hub.desc"),
                    bot=usd["bot"], mid=usd["mid_market"], usd=usd, summary=self.summary(lc, "USD", usd["bot"]),
                    chart30=c30[1], others=[(c, L[c]) for c in self.hub if c != "USD"],
                    js_live=self.live_js(lc))
        # currency pages
        for ccy in self.hub:
            e = L[ccy]
            ch = self.ccy_charts(lc, ccy)
            tabs = [(lc.t(f"range.{k}"), svg) for k, svg, _ in ch]
            mean = e["bot"]["mean"]
            self.render(lc, "ccy", f"/{ccy.lower()}/", "currency.html",
                        lc.t("ccy.title", name=lc.t(f"ccy.{ccy}"), code=ccy), lc.t("ccy.desc", name=lc.t(f"ccy.{ccy}"), code=ccy, rate=lc.rate(mean), date=lc.date(e["bot"]["date"])),
                        ccy=ccy, entry=e, bot=e["bot"], mid=e.get("mid_market"), summary=self.summary(lc, ccy, e["bot"]),
                        tabs=tabs, has_mid_overlay=any(o for _, _, o in ch[:2]),
                        common_f=[(a, a * mean) for a in (1, 10, 50, 100, 500, 1000)],
                        common_t=[(a, a / mean) for a in (10000, 50000, 100000, 500000, 1000000)])
        # converter
        quick = [(c, [a * L[c]["bot"]["mean"] for a in (1, 10, 100, 1000)]) for c in self.hub]
        self.render(lc, "converter", "/kikokotoo/", "converter.html", lc.t("conv.title"), lc.t("conv.desc"),
                    default_ccy="USD", quick=quick)
        # banks
        cheapest, entries = [], []
        for c in self.hub:
            e = L[c]
            entries.append((c, e))
            fresh = {b: r for b, r in e.get("banks", {}).items() if r["fresh"]}
            if len(fresh) >= 2:
                sp = {b: round(r["spread"]["pct"], 4) for b, r in fresh.items()}
                lo, hi = min(sp.values()), max(sp.values())
                cheapest.append((c, {"pct": lo, "banks": sorted(b for b, v in sp.items() if v == lo)},
                                 {"pct": hi, "banks": sorted(b for b, v in sp.items() if v == hi)}))
        b30 = [(r[0], r[2] - r[1]) for r in self.series("bot-usd-30d")]
        starts = [r["date"] for b in self.banks for r in store.read_history(b)]
        self.render(lc, "banks", "/benki/", "banks.html", lc.t("banks.title"), lc.t("banks.desc"),
                    cheapest=cheapest, hub_entries=entries, bank_start=min(starts),
                    bot_spread_chart=charts.chart_pair(b30, "30d", lc, lc.t("banks.chart_title"), lc.t("banks.chart_title"), dp=2))
        # history
        tables, months = [], lc.raw("months.short")
        for c in self.hub:
            by = defaultdict(dict)
            for m, v in self.series(f"bot-{c.lower()}-monthly"):
                by[int(m[:4])][int(m[5:]) - 1] = v
            rows = []
            for y in sorted(by, reverse=True):
                vals = [by[y].get(i) for i in range(12)]
                have = [v for v in vals if v is not None]
                rows.append((y, vals, sum(have) / len(have)))
            tables.append((c, rows))
        usd_rows = {y: avg for y, _, avg in tables[0][1]}
        ypts = [(f"{y}-07-01", usd_rows[y]) for y in sorted(usd_rows)]
        self.render(lc, "history", "/historia/", "history.html", lc.t("hist.title"), lc.t("hist.desc"),
                    tables=tables, months=months,
                    year_chart=charts.chart_pair(ypts, "max", lc, lc.t("hist.year_title"), lc.t("hist.year_title"), dp=0))
        # methodology
        srcs = [{"key": k, "name": n, "url": u, "last_success": self.status.get(sk, {}).get("last_success_at")} for k, n, u, sk in SOURCES]
        n_ex = sum(len(v) for g in self.quality.values() if isinstance(g, dict) for v in g.values() if isinstance(v, dict))
        today = lc.date(datetime.now(timezone.utc).date())
        self.render(lc, "method", "/mbinu/", "method.html", lc.t("method.title"), lc.t("method.desc"),
                    sources=srcs, excluded=n_ex,
                    cite=lc.t("method.cite_text", site=lc.t("site.title"), url=self.abs_url(lc.code, "/"), date=today))

    def live_js(self, lc):
        js = (ROOT / "templates" / "live.js").read_text()
        return (js.replace("__MONTHS__", json.dumps(lc.raw("months.short"), ensure_ascii=False))
                  .replace("__LOC__", json.dumps(lc.raw("format.intl"))).replace("__BASE__", self.base_path + "/"))

    # ---- assets / meta files -------------------------------------------
    def copy_data(self):
        (SITE / "api" / "series").mkdir(parents=True, exist_ok=True)
        (SITE / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy(OUT / "latest.json", SITE / "api" / "latest.json")
        for f in (OUT / "series").glob("*.json"):
            shutil.copy(f, SITE / "api" / "series" / f.name)
        shutil.copy(OUT / "csv" / "bot-monthly-mean.csv", SITE / "data" / "bot-monthly-mean.csv")
        (SITE / ".nojekyll").write_text("")
        if self.preview:
            (SITE / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
        else:
            urls = "".join(f"<url><loc>{self.abs_url(l, p)}</loc></url>" for l, p in self.pages)
            (SITE / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
            (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {self.base_url}/sitemap.xml\n")

    def build(self):
        if SITE.exists():
            shutil.rmtree(SITE)
        SITE.mkdir()
        for lc in self.locales.values():
            self.build_pages(lc)
        self.copy_data()
        return {c: lc.used for c, lc in self.locales.items()}
