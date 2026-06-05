#!/usr/bin/env python3
"""
Export cached YouTuber financial data to Google Sheets.

Setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create a project (or pick an existing one)
  3. Enable the Google Sheets API for the project
  4. Go to IAM & Admin > Service Accounts > Create Service Account
  5. Give it any name, click through to finish
  6. Open the service account, go to Keys > Add Key > Create new key > JSON
  7. Save the downloaded file as  scripts/credentials.json
  8. Create a new Google Sheet and copy its ID from the URL:
       https://docs.google.com/spreadsheets/d/<THIS_PART>/edit
  9. Share the sheet with the service account email (shown in the JSON as "client_email")
     — give it Editor access
 10. Add to .env:
       GOOGLE_SHEET_ID=<sheet id from step 8>

Then run:
    python scripts/export_to_sheets.py
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("Missing dependencies. Run:  pip install gspread google-auth")
    sys.exit(1)

DB_PATH = Path(__file__).parent.parent / "data" / "cache.db"
CREDS_PATH = Path(__file__).parent / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _read_cache(key: str):
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    value, expires_at = row
    if 0 < expires_at < time.time():
        return None
    return json.loads(value)


def main():
    if not CREDS_PATH.exists():
        print(f"ERROR: credentials.json not found at {CREDS_PATH}")
        print("See setup instructions at the top of this file.")
        sys.exit(1)

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("ERROR: GOOGLE_SHEET_ID not set in .env")
        sys.exit(1)

    from app.youtubers import YOUTUBERS

    summary_rows = []
    company_rows = []

    for yt in YOUTUBERS:
        slug = _slugify(yt["name"])
        data = _read_cache(f"youtuber:{slug}")
        if not data:
            print(f"  SKIP {yt['name']} — no cache (run prefetch_all.py first)")
            continue

        summary_rows.append([
            yt["group"],
            yt["name"],
            yt["real_name"],
            data["total_companies"],
            data["total_net_assets"],
            data.get("fetched_at", ""),
        ])

        for company in data.get("companies", []):
            bs = company.get("balance_sheet") or {}
            company_rows.append([
                yt["group"],
                yt["name"],
                company["name"].title(),
                company["number"],
                company.get("role", ""),
                company.get("appointed_on", ""),
                bs.get("net_assets", ""),
                bs.get("net_assets_prior", ""),
                bs.get("date") or company.get("filing_date", ""),
            ])

    print(f"Cached data for {len(summary_rows)}/{len(YOUTUBERS)} YouTubers")
    print(f"Total company rows: {len(company_rows)}")

    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    # Summary tab
    try:
        ws = sh.worksheet("Summary")
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet("Summary", rows=200, cols=10)

    ws.update(
        "A1",
        [["Group", "YouTuber", "Real Name", "Companies", "Total Net Assets (£)", "Last Fetched"]]
        + summary_rows,
    )
    print(f"Written {len(summary_rows)} rows → Summary")

    # Companies tab
    try:
        ws2 = sh.worksheet("Companies")
        ws2.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws2 = sh.add_worksheet("Companies", rows=2000, cols=15)

    ws2.update(
        "A1",
        [["Group", "YouTuber", "Company Name", "Company Number", "Role",
          "Appointed On", "Net Assets (£)", "Prior Year (£)", "Filing Date"]]
        + company_rows,
    )
    print(f"Written {len(company_rows)} rows → Companies")

    print(f"\nDone! https://docs.google.com/spreadsheets/d/{sheet_id}")


if __name__ == "__main__":
    main()
