"""Non-destructive quality flags applied when building series. Stored history is never edited."""
import statistics as st


def spikes(series, window=3, pct=25.0):
    """series: [(date, value)] sorted. Flags points further than pct% from the median of the
    surrounding `window` observations on each side (catches one-day decimal typos)."""
    bad = {}
    vals = [v for _, v in series]
    for i, (d, v) in enumerate(series):
        nb = vals[max(0, i - window):i] + vals[i + 1:i + 1 + window]
        if len(nb) >= 2:
            m = st.median(nb)
            if m and abs(v / m - 1) * 100 > pct:
                bad[d] = f"{abs(v / m - 1) * 100:.1f}% from neighbouring median {m:.4g}"
    return bad


def diverging(mid, official, pct=5.0):
    """Mid-market points more than pct% away from the official rate IN EFFECT that day
    (last published on or before it). mid: {date: v}; official: {date: v}."""
    import bisect
    od = sorted(official)
    bad = {}
    for d, v in mid.items():
        i = bisect.bisect_right(od, d) - 1
        if i < 0:
            continue
        o = official[od[i]]
        if o and abs(v / o - 1) * 100 > pct:
            bad[d] = f"{(v / o - 1) * 100:+.1f}% vs official {o} (published {od[i]})"
    return bad
