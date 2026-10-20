"""Server-rendered inline SVG line charts: no JavaScript, no libraries, tiny."""
import math
from datetime import date, timedelta

# Two geometries so text stays readable: the SVG scales with its box, so the phone version is drawn
# at about phone width and the desktop version wider. CSS shows the right one.
SIZES = {"m": dict(W=360, H=230, L=42, R=10, T=12, B=26, n=3), "d": dict(W=720, H=270, L=58, R=16, T=14, B=30, n=4)}


def _ord(d):
    return date.fromisoformat(d).toordinal()


def nice_ticks(lo, hi, n=4):
    if hi - lo <= 0:
        hi, lo = hi + 1, lo - 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 0.999:
        ticks.append(round(v, 10))
        v += step
    return ticks, step


def _x_ticks(kind, d0, d1):
    a, b = date.fromordinal(d0), date.fromordinal(d1)
    out = []
    if kind == "30d":
        d = b
        while d >= a:
            out.append(d)
            d -= timedelta(days=7)
        return [(x.toordinal(), "d", x) for x in reversed(out)]
    if kind == "1y":
        y, m = a.year, a.month
        m += 1
        while True:
            if m > 12:
                y, m = y + 1, 1
            d = date(y, m, 1)
            if d > b:
                break
            if m % 2 == 1:
                out.append((d.toordinal(), "m", d))
            m += 1
        return out
    span = b.year - a.year
    step = 1 if span <= 10 else (2 if span <= 20 else 5)
    first = (a.year // step + 1) * step
    return [(date(y, 1, 1).toordinal(), "y", date(y, 1, 1)) for y in range(first, b.year + 1, step)]


def chart_pair(*a, **kw):
    """Phone and desktop variants of the same chart."""
    return (f'<div class="ch-m">{line_chart(*a, size="m", **kw)}</div>'
            f'<div class="ch-d">{line_chart(*a, size="d", **kw)}</div>')


def line_chart(points, kind, lc, title, desc, series2=None, dp=2, size="m"):
    """points: [(iso_date, value)]. series2: optional dashed second line (same kind)."""
    z = SIZES[size]
    W, H, L, R, T, B = z["W"], z["H"], z["L"], z["R"], z["T"], z["B"]
    if len(points) < 2:
        return f'<p class="muted">{lc.t("chart.not_enough")}</p>'
    pts = [(_ord(d), v) for d, v in points]
    s2 = [(_ord(d), v) for d, v in (series2 or []) if pts[0][0] <= _ord(d) <= pts[-1][0]]
    allv = [v for _, v in pts] + [v for _, v in s2]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.08 or hi * 0.01
    ticks, step = nice_ticks(lo - pad, hi + pad, z["n"])
    axis_dp = 0 if step >= 1 else min(4, math.ceil(-math.log10(step)))
    y0, y1 = ticks[0], ticks[-1]
    x0, x1 = pts[0][0], pts[-1][0]
    sx = lambda o: L + (o - x0) / (x1 - x0) * (W - L - R)
    sy = lambda v: T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
    g = []
    for v in ticks:
        y = sy(v)
        g.append(f'<line class="c-grid" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                 f'<text class="c-ax" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{lc.num(v, axis_dp)}</text>')
    for o, k, d in _x_ticks(kind, x0, x1):
        if not (x0 <= o <= x1):
            continue
        lab = str(d.day) + " " + lc.raw("months.short")[d.month - 1] if k == "d" else (
            lc.raw("months.short")[d.month - 1] if k == "m" else str(d.year))
        x = sx(o)
        anchor = "end" if x > W - R - 18 else ("start" if x < L + 4 else "middle")
        g.append(f'<text class="c-ax" x="{x:.1f}" y="{H - 8}" text-anchor="{anchor}">{lab}</text>')
    poly = " ".join(f"{sx(o):.1f},{sy(v):.1f}" for o, v in pts)
    area = f"{sx(x0):.1f},{sy(y0):.1f} {poly} {sx(x1):.1f},{sy(y0):.1f}"
    g.append(f'<polygon class="c-area" points="{area}"/><polyline class="c-line" points="{poly}"/>')
    if s2:
        g.append(f'<polyline class="c-line2" points="{" ".join(f"{sx(o):.1f},{sy(v):.1f}" for o, v in s2)}"/>')
    lx, ly = sx(x1), sy(pts[-1][1])
    g.append(f'<circle class="c-dot" cx="{lx:.1f}" cy="{ly:.1f}" r="3.5"/>'
             f'<text class="c-last" x="{lx - 6:.1f}" y="{max(ly - 9, 12):.1f}" text-anchor="end">{lc.num(pts[-1][1], dp)}</text>')
    full = f"{title}. {desc}"
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{full}" xmlns="http://www.w3.org/2000/svg">'
            f'<title>{title}</title><desc>{desc}</desc>{"".join(g)}</svg>')
