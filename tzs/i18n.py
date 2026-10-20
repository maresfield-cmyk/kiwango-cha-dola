"""Locale loading and number/date formatting. All user-facing text lives in locales/*.json."""
import json
from datetime import date, datetime, timedelta, timezone

from . import store

EAT = timezone(timedelta(hours=3))


class Locale:
    def __init__(self, code):
        self.code = code
        self.s = json.loads((store.ROOT / "locales" / f"{code}.json").read_text())
        self.used = set()

    def t(self, key, **kw):
        if key not in self.s:
            raise KeyError(f"missing string '{key}' in locales/{self.code}.json")
        self.used.add(key)
        v = self.s[key]
        return v.format(**kw) if kw else v

    def raw(self, key):
        self.used.add(key)
        return self.s[key]

    # --- numbers -----------------------------------------------------------
    def _sep(self, txt):
        g, d = self.s["format.group"], self.s["format.decimal"]
        return txt.replace(",", "\0").replace(".", d).replace("\0", g)

    def num(self, v, dp=2):
        return "" if v is None else self._sep(f"{v:,.{dp}f}")

    def rate(self, v):
        """Headline precision: 2 decimals for large rates, 4 for small ones (UGX, KES...)."""
        return "" if v is None else self.num(v, 2 if v >= 100 else 4)

    def pub(self, v):
        """Exactly as BoT publishes: 4 decimals."""
        return self.num(v, 4)

    def signed(self, v, dp=2, suffix=""):
        if v is None:
            return ""
        s = self.num(abs(v), dp)
        sign = "+" if v > 0 else ("−" if v < 0 else "")
        return f"{sign}{s}{suffix}"

    def pct(self, v, dp=2):
        return self.signed(v, dp, "%")

    # --- dates -------------------------------------------------------------
    def date(self, d):
        d = date.fromisoformat(d) if isinstance(d, str) else d
        return f"{d.day} {self.raw('months.short')[d.month - 1]} {d.year}"

    def month(self, ym):
        y, m = ym.split("-")
        return f"{self.raw('months.short')[int(m) - 1]} {y}"

    def dt(self, iso):
        if not iso:
            return ""
        u = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(EAT)
        return f"{u.day} {self.raw('months.short')[u.month - 1]} {u.year}, {u:%H:%M} EAT"


def direction(pct, eps=0.005):
    """up = shilling weaker (the X/TZS rate rose), down = shilling stronger."""
    if pct is None:
        return "flat"
    return "up" if pct > eps else ("down" if pct < -eps else "flat")
