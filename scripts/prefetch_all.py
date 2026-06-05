#!/usr/bin/env python3
"""
Pre-fetch all YouTubers' company data into the local cache.
Run this before deploying with READ_ONLY=true so the site serves instantly.

Usage:
    python scripts/prefetch_all.py
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.cache import cache_get, init_cache
from app.youtubers import YOUTUBERS


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def main():
    await init_cache()

    # Import after init so the app module is ready
    from app.routes import _fetch_youtuber

    total = len(YOUTUBERS)
    for i, yt in enumerate(YOUTUBERS, 1):
        slug = _slugify(yt["name"])
        cached = await cache_get(f"youtuber:{slug}")
        if cached:
            print(f"[{i}/{total}] CACHED   {yt['name']}")
            continue

        print(f"[{i}/{total}] FETCHING {yt['name']}...", end="", flush=True)
        await _fetch_youtuber(slug)
        result = await cache_get(f"youtuber:{slug}")
        if result:
            companies = result.get("total_companies", 0)
            net = result.get("total_net_assets", 0)
            print(f"  {companies} companies, £{net:,}")
        else:
            print("  FAILED")

    print("\nDone. Deploy with READ_ONLY=true to serve from this cache.")


if __name__ == "__main__":
    asyncio.run(main())
