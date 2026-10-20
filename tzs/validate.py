"""Row validation. A bad row never reaches history; an anomaly keeps the previous value."""
from .store import _ref


def validate(rows, prev, anomaly_pct):
    """prev: {currency: last stored row}. Returns (ok, rejected, anomalies);
    rejected/anomalies are (row, reason) pairs."""
    ok, rejected, anomalies = [], [], []
    for r in rows:
        b, s, m = r["buying"], r["selling"], r["mean"]
        vals = [float(v) for v in (b, s, m) if v not in (None, "")]
        if not vals or any(v <= 0 for v in vals):
            rejected.append((r, "non_positive_or_missing"))
            continue
        if b not in (None, "") and s not in (None, "") and float(b) > float(s):
            rejected.append((r, "buying_above_selling"))
            continue
        p, new = prev.get(r["currency"]), _ref(r)
        old = _ref(p) if p else None
        if old and abs(new - old) / old * 100 > anomaly_pct:
            anomalies.append((r, f"moved {abs(new - old) / old * 100:.2f}% from {old} (> {anomaly_pct}%)"))
            continue
        ok.append(r)
    return ok, rejected, anomalies
