"""Run: python3 -m unittest discover -s tests   (from tzs-tracker/)
Fixtures are real captures from 2026-10-19 so a site layout change shows up as a failing test."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from tzs import quality, validate  # noqa: E402
from tzs.sources import banks, bot  # noqa: E402


def fx(name):
    with open(os.path.join(HERE, "fixtures", name), "rb") as f:
        return f.read()


class BotTests(unittest.TestCase):
    def test_live_table(self):
        rows = bot._keep(bot.parse_table(fx("bot_live.html")))
        usd = next(r for r in rows if r["currency"] == "USD")
        self.assertEqual((usd["buying"], usd["selling"], usd["mean"], usd["date"]), (2622.4752, 2648.7, 2635.5876, "2026-10-19"))
        self.assertEqual(len(rows), 38)
        self.assertNotIn("GOLD", {r["currency"] for r in rows})

    def test_classify_drops_padded_days_but_keeps_saturday_change(self):
        def day(d, v):
            return [{"currency": "USD", "date": d, "buying": v, "selling": v + 1, "mean": v + .5}]
        # Fri new, Sat new (history labels run a day behind), Sun/Mon padded, Tue new
        rows = sum([day("2025-03-07", 1), day("2025-03-08", 2), day("2025-03-09", 2), day("2025-03-10", 2), day("2025-03-11", 3)], [])
        real, rep, _ = bot.classify_days(rows, "2025-03-07", "2025-03-11")
        self.assertEqual(real, ["2025-03-07", "2025-03-08", "2025-03-11"])
        self.assertEqual(rep["carried_dates"], 2)

    def test_two_digit_year_pivot(self):
        self.assertEqual(bot._date("07-Jan-00"), "2000-01-07")
        self.assertEqual(bot._date("08-Sep-99"), "1999-09-08")


class BankTests(unittest.TestCase):
    def test_crdb(self):
        rows, day, published = banks.parse_crdb(fx("crdb.html"))
        usd = next(r for r in rows if r[0] == "USD")
        self.assertEqual(usd[1:3], (2590.0, 2670.0))
        self.assertEqual(day, "2026-10-19")
        self.assertEqual(published, "")  # the page stamp is render time, never a publish time

    def test_nbc_uses_tt_columns_and_first_usd_row(self):
        rows, day, published = banks.parse_nbc(fx("nbc.pdf"))
        d = {r[0]: r for r in rows}
        self.assertEqual((d["USD"][1], d["USD"][2]), (2590.0, 2670.0))
        self.assertAlmostEqual(d["EUR"][1], 2797.79570)
        self.assertEqual(day, "2026-10-19")
        self.assertEqual(published, "2026-10-19T06:30:00Z")  # 09:30 EAT
        self.assertEqual(len([r for r in rows if r[0] == "USD"]), 1)

    def test_stanbic_split_digits(self):
        rows, day, _ = banks.parse_stanbic(fx("stanbic.pdf"))
        d = {r[0]: r for r in rows}
        self.assertEqual((d["JPY"][1], d["JPY"][2]), (16.54, 20.99))   # PDF text is '2 0.99'
        self.assertEqual(d["KES"][2], 25.55)
        self.assertEqual(d["UGX"][2], 0.72)                              # PDF text is '0 .72'
        self.assertEqual(day, "2026-10-19")


class ValidationTests(unittest.TestCase):
    def row(self, c, b, s, m=None):
        return {"currency": c, "buying": b, "selling": s, "mean": m, "date": "2026-10-20"}

    def test_rules(self):
        prev = {"USD": {"buying": 2590, "selling": 2670, "mean": None}}
        ok, rej, anom = validate.validate([self.row("USD", 2600, 2680), self.row("USD", 2800, 2900),
                                           self.row("EUR", 0, 5), self.row("GBP", 10, 9)], prev, 3.0)
        self.assertEqual(len(ok), 1)
        self.assertEqual([r[1] for r in rej], ["non_positive_or_missing", "buying_above_selling"])
        self.assertEqual(len(anom), 1)


class QualityTests(unittest.TestCase):
    def test_decimal_typo_flagged(self):
        s = [(f"2000-07-0{i}", v) for i, v in enumerate([799.5, 799.4, 7.9951, 799.3, 799.2, 799.1], 1)]
        self.assertEqual(list(quality.spikes(s)), ["2000-07-03"])


if __name__ == "__main__":
    unittest.main()
