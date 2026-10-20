#!/usr/bin/env bash
# One-command local run on a Mac: creates a venv, installs deps, runs tests, one fetch cycle, builds out/.
# First run only (history): python3 scripts/backfill_bot.py && python3 scripts/backfill_midmarket.py
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/fetch.py
.venv/bin/python scripts/preview_chart.py
