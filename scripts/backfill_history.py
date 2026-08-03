#!/usr/bin/env python3
"""
Rebuild data/history.json from the real filing history already present in
data/youtubers/*.json — each company's all_balance_sheets holds every
historical filing Companies House has on record, each carrying its own
prior-year comparison figures straight from the accounts PDF.

This reconstructs what the weekly refresh would have reported for every
week going back N months, using genuine filing dates rather than our own
fetch schedule.

Usage:
    python scripts/backfill_history.py [months]   # default 24
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "youtubers"
HISTORY_PATH = Path(__file__).parent.parent / "data" / "history.json"


def _next_sunday_on_or_after(d: date) -> date:
    """The weekly refresh cron runs Sundays — bucket each filing under the
    first Sunday on/after it, i.e. the run that would have picked it up."""
    return d + timedelta(days=(6 - d.weekday()) % 7)


def main():
    months = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    cutoff = date.today() - timedelta(days=months * 30)

    runs: dict[str, list] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        d = json.loads(path.read_text())
        for c in d.get("companies", []):
            for bs in c.get("all_balance_sheets", []):
                fd_str = bs.get("_filing_date")
                if not fd_str:
                    continue
                try:
                    fd = date.fromisoformat(fd_str)
                except ValueError:
                    continue
                if fd < cutoff:
                    continue

                net_assets, prev = bs.get("net_assets"), bs.get("net_assets_prior")
                if net_assets is None or prev is None:
                    continue  # only record events where a real change is known

                run_at = _next_sunday_on_or_after(fd).isoformat()
                runs.setdefault(run_at, []).append({
                    "slug": d["slug"],
                    "name": d["name"],
                    "group": d["group"],
                    "company_name": c.get("name"),
                    "company_number": c.get("number"),
                    "filing_date": fd_str,
                    "period_date": bs.get("date"),
                    "net_assets": net_assets,
                    "prev_net_assets": prev,
                })

    history = [
        {
            "run_at": run_at,
            "changes": sorted(changes, key=lambda c: c["filing_date"], reverse=True),
        }
        for run_at, changes in sorted(runs.items())
    ]
    HISTORY_PATH.write_text(json.dumps(history, indent=2, default=str))
    total = sum(len(r["changes"]) for r in history)
    print(f"Wrote {len(history)} weekly runs, {total} change events, back to {cutoff}")


if __name__ == "__main__":
    main()
