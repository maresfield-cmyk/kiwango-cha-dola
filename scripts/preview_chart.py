#!/usr/bin/env python3
"""Standalone SVG preview of the USD history (BoT full history; BoT vs mid-market since 2024)."""
import json
import os
import sys
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
S = lambda n: json.load(open(os.path.join(ROOT, "out", "series", n)))
W, H, PAD = 1000, 300, (60, 20, 30, 40)  # left, right, top, bottom


def ordinal(d):
    return date.fromisoformat(d).toordinal()


def chart(title, layers, x0, x1, ymin, ymax, marks=()):
    l, r, t, b = PAD
    sx = lambda d: l + (ordinal(d) - x0) / (x1 - x0) * (W - l - r)
    sy = lambda v: t + (1 - (v - ymin) / (ymax - ymin)) * (H - t - b)
    g = [f'<text x="{l}" y="14" font-size="14" font-weight="600" fill="#e6edf3">{title}</text>']
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        y = sy(v)
        g.append(f'<line x1="{l}" x2="{W - r}" y1="{y:.1f}" y2="{y:.1f}" stroke="#2a3441"/><text x="{l - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#8b98a8">{v:,.0f}</text>')
    y0, y1 = date.fromordinal(x0).year, date.fromordinal(x1).year
    step = max(1, (y1 - y0) // 8)
    for yr in range(y0 + 1, y1 + 1, step):
        x = sx(f"{yr}-01-01")
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{t}" y2="{H - b}" stroke="#222b36"/><text x="{x:.1f}" y="{H - b + 16}" text-anchor="middle" font-size="11" fill="#8b98a8">{yr}</text>')
    for name, color, pts in layers:
        pts = [p for p in pts if x0 <= ordinal(p[0]) <= x1]
        g.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{" ".join(f"{sx(d):.1f},{sy(v):.1f}" for d, v in pts)}"/>')
    for d, v in marks:
        g.append(f'<circle cx="{sx(d):.1f}" cy="{sy(min(max(v, ymin), ymax)):.1f}" r="3" fill="none" stroke="#ff6b6b"/>')
    lx = l + 8
    for name, color, _ in layers:
        g.append(f'<rect x="{lx}" y="{t + 6}" width="12" height="3" fill="{color}"/><text x="{lx + 17}" y="{t + 11}" font-size="11" fill="#c9d4e0">{name}</text>')
        lx += 20 + len(name) * 6.5
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="background:#161d27;border-radius:10px;margin:14px 0">{"".join(g)}</svg>'


bot = S("bot-usd.json")["rows"]
mid = S("mid-usd.json")["rows"]
q = json.load(open(os.path.join(ROOT, "out", "quality.json")))
botm = [(r[0], r[3]) for r in bot]
x0, x1 = ordinal(botm[0][0]), ordinal(botm[-1][0])
c1 = chart("USD/TZS: Bank of Tanzania mean rate, full history (1999 - today)", [("BoT mean", "#4dd0e1", botm)], x0, x1, 600, 2800)
m0 = ordinal("2024-03-02")
sub = [p for p in botm if ordinal(p[0]) >= m0]
vals = [v for _, v in sub] + [r[1] for r in mid]
c2 = chart("USD/TZS since March 2024: BoT mean vs mid-market (fawazahmed0). Red circles = mid-market days excluded as bad data",
           [("BoT mean", "#4dd0e1", sub), ("Mid-market", "#ffb74d", [(d, v) for d, v in mid])], m0, x1, 2200, 2750,
           [(d, 2400) for d in q["midmarket"]["USD"]])
html = f'''<!doctype html><meta charset="utf-8"><title>USD/TZS history preview</title>
<body style="margin:0;padding:24px;background:#0d1117;color:#c9d4e0;font:14px/1.5 -apple-system,system-ui,sans-serif">
<h2 style="margin:0 0 4px;color:#e6edf3">USD/TZS backfilled history</h2>
<div style="color:#8b98a8">{len(botm)} BoT observations ({botm[0][0]} to {botm[-1][0]}), {len(mid)} mid-market days. Preview only.</div>{c1}{c2}'''
os.makedirs(os.path.join(ROOT, "out", "preview"), exist_ok=True)
open(os.path.join(ROOT, "out", "preview", "usd-history.html"), "w").write(html)
print("wrote out/preview/usd-history.html")
