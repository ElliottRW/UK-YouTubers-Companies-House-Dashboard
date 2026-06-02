# UK YouTubers Companies House Dashboard

A web app that automatically pulls every UK company a YouTuber is linked to from Companies House, reads the latest balance sheet from the filed iXBRL accounts, and displays everything in a clean dashboard.

> Built after the [Reddit post](https://reddit.com) that showed how you can look up YouTuber finances on Companies House — this automates it for any group.

![Dashboard showing Sidemen members and their company net assets](https://placeholder.com/screenshot)

## What it does

1. You give it a **seed company** (e.g. Sidemen Holdings Limited — `12129201`)
2. It finds all current officers/members of that company
3. For each person it discovers **every UK company** they're linked to via the Companies House API
4. It downloads the latest accounts filing for each company and reads the balance sheet from the iXBRL data
5. Everything is displayed in a clean dashboard with year-on-year comparisons
6. Data is cached — first load takes 1–3 minutes, subsequent loads are instant
7. New companies appear automatically on the next hourly refresh

## Setup

### 1. Get a free Companies House API key

- Go to [developer.company-information.service.gov.uk](https://developer.company-information.service.gov.uk/)
- Register → Create an application (choose **Live** environment) → Create new key → select **REST**
- Copy the key shown (it's only displayed once)

### 2. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Add your API key

```bash
cp .env.example .env
# Edit .env and replace the placeholder with your actual key
```

`.env` should look like:
```
CH_API_KEY=your-actual-key-here
```

### 4. Run

```bash
python main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Adding groups

The app comes pre-loaded with **The Sidemen** (seed company: Sidemen Holdings Limited). To add another group:

1. Find the group's main holding company on [Companies House](https://find-and-update.company-information.service.gov.uk/)
2. Click **"+ Add a Group"** on the homepage
3. Enter the company number and a display name

Any UK YouTuber or creator group with a UK company structure will work.

## How the balance sheet data is sourced

All data comes directly from **Companies House** via their official API. The app reads iXBRL (inline XBRL) filings — the structured data format that UK companies use when filing accounts — rather than trying to scrape PDFs. This makes the numbers reliable and machine-readable.

Note: figures are shown in **full pounds** (£). Many filings report in £'000, which the app converts automatically.

## Tech stack

- **Python** + **FastAPI** — async backend
- **httpx** — concurrent Companies House API calls
- **SQLite** — caching (so you don't hammer the API on every page load)
- **Jinja2** + **Tailwind CSS** — server-rendered templates, no build step

## Rate limits

The Companies House free API allows 600 requests per 5 minutes. For a group with ~7 members who each have ~5 companies, a full fetch uses ~100–150 requests. You won't hit the limit in normal use.

## Contributing

PRs welcome. Some ideas:
- Export to CSV/Excel
- Chart net assets over time (multiple years of filings)
- Flag dissolved companies
- Add profit & loss data (where available in the iXBRL)
- Support for LLP accounts
