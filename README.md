# TZS exchange-rate tracker (data pipeline)

Free, keyless sources only. Python 3.9+, `lxml` and `pdfplumber`.

```
python3 scripts/fetch.py                  # one cycle: BoT live, mid-market, CRDB, NBC, Stanbic -> data/history, then out/
python3 scripts/backfill_bot.py           # BoT history 1999 -> today (cached; past years never re-fetched)
python3 scripts/backfill_midmarket.py     # daily mid-market since 2024-03-02
python3 scripts/build_out.py              # rebuild out/ from stored history, no network
python3 scripts/preview_chart.py          # out/preview/usd-history.html
python3 -m unittest discover -s tests     # parsers against real captured fixtures
python3 discovery/discover.py             # re-verify every source is still reachable/parseable
```

## Layout
- `data/raw/`      every fetched response, gzipped, never re-fetched for past days
- `data/history/<source>/<year>.csv`  append-only observations (`source,currency,date,buying,selling,mean,observed_at,published_at,source_url,origin,flags`)
- `data/alerts.jsonl`  rejected rows, anomalies (>3% move), failed sources
- `data/reports/`  backfill audit reports
- `out/`           everything the site publishes (`latest.json`, `series/`, `csv/`, `quality.json`, `reconcile.json`, `status.json`)

## Rules worth knowing
- `origin`: `live` (captured by this pipeline) or `backfill` (BoT history form / fawazahmed0 dated snapshots).
- `flags`: `carried` (BoT showed a new date with identical numbers), `wide_spread` (bank spread >25%), `tt` (NBC telegraphic-transfer basis).
- Stored history is never edited. Source typos are excluded when `out/` is built and listed in `out/quality.json`.
- A failing source keeps its last good value; the others still run; `out/status.json` records why.
