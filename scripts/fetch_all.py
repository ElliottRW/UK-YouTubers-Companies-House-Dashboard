#!/usr/bin/env python3
"""
Fetch all YouTuber data from Companies House and save as static JSON files.

The web app serves these files directly — no API key or live CH calls needed
when deployed.  Balance-sheet PDFs are cached in data/cache.db so only new
filings are downloaded on subsequent runs.

Rate limit: 1.5 API calls/second (90/min — well under CH's 600/5min limit).
Cold-cache first run: ~20-40 min depending on how many historical filings exist.
Warm-cache re-run: a few minutes (only changed companies hit the API).

Usage:
    python scripts/fetch_all.py              # all YouTubers
    python scripts/fetch_all.py ksi callux   # specific slugs only
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from app.cache import cache_get, cache_set, init_cache
from app.client import CHClient
from app.parser import extract_balance_sheet
from app.youtubers import YOUTUBERS

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "youtubers"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class _ThrottledClient(CHClient):
    """CHClient that serialises all _get() calls through a 1.5 req/s rate limit."""

    def __init__(self, rate: float = 1.5):
        self._interval = 1.0 / rate
        self._last = 0.0
        self._lock: Optional[asyncio.Lock] = None  # created lazily inside the loop

    async def _get(self, url, params=None):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
        return await super()._get(url, params)


async def _fetch_one(yt: dict, client: _ThrottledClient) -> Optional[dict]:
    api_sem = asyncio.Semaphore(3)
    pdf_sem = asyncio.Semaphore(2)

    # Locate this person's officer record in their seed company
    officers = await client.get_officers(str(yt["seed_company"]))
    surname_upper = yt["surname"].upper()
    officer = next(
        (o for o in officers if surname_upper in o.get("name", "").upper()),
        None,
    )
    if not officer:
        print(f"    WARNING: '{surname_upper}' not found in company {yt['seed_company']}")
        return None

    officer_id = client.extract_officer_id(officer)
    if not officer_id:
        print(f"    WARNING: could not extract officer ID")
        return None

    async with api_sem:
        appointments = await client.get_appointments(officer_id)

    # Merge appointments from any extra seed companies (separate CH officer profiles)
    seen_cns = {a.get("appointed_to", {}).get("company_number") for a in appointments}
    for extra_cn in yt.get("extra_seed_companies", []):
        extra_officers = await client.get_officers(str(extra_cn))
        extra_officer = next(
            (o for o in extra_officers if surname_upper in o.get("name", "").upper()), None
        )
        if extra_officer:
            extra_id = client.extract_officer_id(extra_officer)
            if extra_id and extra_id != officer_id:
                async with api_sem:
                    extra_appts = await client.get_appointments(extra_id)
                for appt in extra_appts:
                    cn = appt.get("appointed_to", {}).get("company_number")
                    if cn and cn not in seen_cns:
                        appointments.append(appt)
                        seen_cns.add(cn)

    active_appts = [
        a for a in appointments
        if not a.get("resigned_on")
        and a.get("appointed_to", {}).get("company_number")
    ]

    async def process_company(appt: dict) -> dict:
        at = appt.get("appointed_to", {})
        cn = at.get("company_number", "")
        entry = {
            "number": cn,
            "name": at.get("company_name", ""),
            "status": at.get("company_status", "active"),
            "role": appt.get("officer_role", ""),
            "appointed_on": appt.get("appointed_on", ""),
            "balance_sheet": None,
            "all_balance_sheets": [],
            "filing_date": None,
            "filing_description": None,
        }

        async with api_sem:
            filings = await client.get_all_accounts_filings(cn)
        if not filings:
            return entry

        entry["filing_date"] = filings[0].get("date")
        entry["filing_description"] = filings[0].get("description", "")

        all_bs = []
        for filing in filings:
            filing_date = filing.get("date", "unknown")
            bs_key = f"bs:{cn}:{filing_date}"

            cached_bs = await cache_get(bs_key)
            if cached_bs:
                all_bs.append({**cached_bs, "_filing_date": filing_date})
                continue

            doc_url = filing.get("links", {}).get("document_metadata", "")
            if not doc_url:
                continue

            async with pdf_sem:
                pdf_bytes = await client.download_pdf(doc_url)
            if not pdf_bytes:
                continue

            bs = extract_balance_sheet(pdf_bytes)
            if bs and "net_assets" in bs:
                await cache_set(bs_key, bs)
                all_bs.append({**bs, "_filing_date": filing_date})

        entry["all_balance_sheets"] = all_bs
        if all_bs:
            entry["balance_sheet"] = all_bs[0]
        return entry

    companies = list(await asyncio.gather(*[process_company(a) for a in active_appts]))
    companies.sort(
        key=lambda c: (c.get("balance_sheet") or {}).get("net_assets") or 0,
        reverse=True,
    )

    return {
        "slug": _slugify(yt["name"]),
        "name": yt["name"],
        "real_name": yt["real_name"],
        "group": yt["group"],
        "officer_name": officer.get("name", ""),
        "officer_id": officer_id,
        "companies": companies,
        "total_companies": len(companies),
        "total_net_assets": sum(
            (c.get("balance_sheet") or {}).get("net_assets") or 0 for c in companies
        ),
        "fetched_at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
    }


async def main():
    slugs = {_slugify(a) for a in sys.argv[1:]} if len(sys.argv) > 1 else None
    targets = [y for y in YOUTUBERS if slugs is None or _slugify(y["name"]) in slugs]

    if not targets:
        print("No matching YouTubers found.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    await init_cache()

    client = _ThrottledClient(rate=1.5)
    total = len(targets)
    saved, failed = 0, 0

    print(f"Fetching {total} YouTubers at ≤1.5 req/s …\n")

    for i, yt in enumerate(targets, 1):
        slug = _slugify(yt["name"])
        print(f"[{i}/{total}] {yt['name']}", end="  ", flush=True)
        t0 = time.monotonic()

        try:
            data = await _fetch_one(yt, client)
        except Exception as exc:
            print(f"ERROR — {exc}")
            failed += 1
            continue

        if not data:
            failed += 1
            continue

        out = OUTPUT_DIR / f"{slug}.json"
        out.write_text(json.dumps(data, indent=2, default=str))

        elapsed = time.monotonic() - t0
        net = data["total_net_assets"]
        print(f"{data['total_companies']} companies  £{net:,}  ({elapsed:.0f}s)")
        saved += 1

    print(f"\n✓ {saved} saved   ✗ {failed} failed")
    print(f"  Output: {OUTPUT_DIR}")
    if saved:
        print("  Commit data/youtubers/ and deploy — no API key needed at runtime.")


if __name__ == "__main__":
    asyncio.run(main())
