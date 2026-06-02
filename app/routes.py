import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .cache import cache_delete_prefix, cache_get, cache_set, init_cache
from .client import CHClient
from .config import add_group, load_groups, remove_group
from .parser import extract_balance_sheet

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

app = FastAPI(title="YouTubers Accounts")

_static = BASE_DIR / "static"
_static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Template filters ──────────────────────────────────────────────────────────

def _fmt_currency(val) -> str:
    try:
        if val is None:
            return "—"
        v = int(val)
        return f"(£{abs(v):,})" if v < 0 else f"£{v:,}"
    except Exception:
        return "—"


def _fmt_name(name: str) -> str:
    """Convert 'SURNAME, Firstname Middle' to 'Firstname Middle Surname'."""
    if not name:
        return name
    if "," in name:
        parts = name.split(",", 1)
        surname = parts[0].strip().title()
        given = parts[1].strip().title()
        return f"{given} {surname}"
    return name.title()


def _fmt_company(name: str) -> str:
    """Title-case a company name."""
    return name.title() if name else name


templates.env.filters["currency"] = _fmt_currency
templates.env.filters["format_name"] = _fmt_name
templates.env.filters["company_name"] = _fmt_company

# ── Fetch status tracker (in-memory, reset on restart) ────────────────────────

_fetch_status: dict[str, str] = {}  # company_number -> "running"|"complete"|"error"


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    await init_cache()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "groups": load_groups()}
    )


@app.post("/group/add")
async def add_group_route(
    company_number: str = Form(...),
    display_name: str = Form(...),
):
    cn = re.sub(r"\s+", "", company_number.strip().upper())
    name = display_name.strip()
    if not name:
        client = CHClient()
        info = await client.get_company(cn)
        name = info.get("company_name", cn)
    add_group(cn, name)
    return RedirectResponse(f"/group/{cn}", status_code=303)


@app.post("/group/{company_number}/delete")
async def delete_group_route(company_number: str):
    remove_group(company_number)
    return RedirectResponse("/", status_code=303)


@app.get("/group/{company_number}", response_class=HTMLResponse)
async def group_page(
    request: Request, company_number: str, background_tasks: BackgroundTasks
):
    groups = load_groups()
    group_cfg = next(
        (g for g in groups if g["company_number"] == company_number), None
    )
    cached = await cache_get(f"group:{company_number}")

    if cached:
        return templates.TemplateResponse(
            "group.html",
            {"request": request, "group": group_cfg, "data": cached, "status": "complete"},
        )

    status = _fetch_status.get(company_number, "idle")
    if status == "idle":
        _fetch_status[company_number] = "running"
        background_tasks.add_task(_fetch_group, company_number)

    return templates.TemplateResponse(
        "group.html",
        {
            "request": request,
            "group": group_cfg,
            "data": None,
            "status": status if status == "error" else "running",
            "company_number": company_number,
        },
    )


@app.get("/api/group/{company_number}/status")
async def group_status(company_number: str):
    cached = await cache_get(f"group:{company_number}")
    if cached:
        return {"status": "complete"}
    return {"status": _fetch_status.get(company_number, "idle")}


@app.post("/group/{company_number}/refresh")
async def refresh_group(company_number: str, background_tasks: BackgroundTasks):
    await cache_delete_prefix(f"group:{company_number}")
    _fetch_status[company_number] = "running"
    background_tasks.add_task(_fetch_group, company_number)
    return RedirectResponse(f"/group/{company_number}", status_code=303)


# ── Core fetch logic ──────────────────────────────────────────────────────────

async def _fetch_group(company_number: str):
    try:
        logger.info(f"[{company_number}] Starting group fetch")
        client = CHClient()
        api_sem = asyncio.Semaphore(5)   # concurrent CH API calls
        pdf_sem = asyncio.Semaphore(3)   # concurrent PDF downloads

        # Seed company
        company_info = await client.get_company(company_number)
        group_name = company_info.get("company_name", company_number)

        # Officers of the seed company (skip resigned)
        officers_raw = await client.get_officers(company_number)
        active_officers = [o for o in officers_raw if not o.get("resigned_on")]
        logger.info(f"[{company_number}] {len(active_officers)} active officers")

        async def process_officer(officer: dict) -> Optional[dict]:
            officer_id = client.extract_officer_id(officer)
            if not officer_id:
                return None
            async with api_sem:
                appointments = await client.get_appointments(officer_id)

            # Company info lives under the "appointed_to" key
            companies_raw = [
                a for a in appointments
                if not a.get("resigned_on")
                and a.get("appointed_to", {}).get("company_status") in ("active", None, "")
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
                    "filing_date": None,
                    "filing_description": None,
                }

                # Balance sheet may already be cached (keyed by company + filing date)
                # We first get the filing to know the date, then check a permanent cache
                async with api_sem:
                    filing = await client.get_latest_accounts_filing(cn)
                if not filing:
                    return entry

                entry["filing_date"] = filing.get("date")
                entry["filing_description"] = filing.get("description", "")
                filing_date = filing.get("date", "unknown")
                bs_key = f"bs:{cn}:{filing_date}"

                cached_bs = await cache_get(bs_key)
                if cached_bs:
                    entry["balance_sheet"] = cached_bs
                    return entry

                doc_url = filing.get("links", {}).get("document_metadata", "")
                if not doc_url:
                    return entry

                async with pdf_sem:
                    pdf_bytes = await client.download_pdf(doc_url)

                if not pdf_bytes:
                    return entry

                bs = extract_balance_sheet(pdf_bytes)
                if bs and "net_assets" in bs:
                    await cache_set(bs_key, bs)  # permanent — old filings never change
                    entry["balance_sheet"] = bs

                return entry

            companies = await asyncio.gather(
                *[process_company(a) for a in companies_raw]
            )
            companies.sort(
                key=lambda c: (c.get("balance_sheet") or {}).get("net_assets") or 0,
                reverse=True,
            )

            officer_total = sum(
                (c.get("balance_sheet") or {}).get("net_assets") or 0
                for c in companies
            )

            return {
                "name": officer.get("name", ""),
                "role": officer.get("officer_role", ""),
                "officer_id": officer_id,
                "companies": companies,
                "total_net_assets": officer_total,
            }

        officer_data = await asyncio.gather(
            *[process_officer(o) for o in active_officers]
        )
        officer_data = [o for o in officer_data if o]

        # Deduplicate companies for the grand total
        seen: dict[str, dict] = {}
        for officer in officer_data:
            for company in officer["companies"]:
                if company["number"] not in seen:
                    seen[company["number"]] = company

        total_net_assets = sum(
            (c.get("balance_sheet") or {}).get("net_assets") or 0
            for c in seen.values()
        )

        result = {
            "company_number": company_number,
            "company_name": group_name,
            "officers": officer_data,
            "total_companies": len(seen),
            "total_net_assets": total_net_assets,
            "fetched_at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        }

        await cache_set(f"group:{company_number}", result, ttl=3600)  # 1-hour TTL
        _fetch_status[company_number] = "complete"
        logger.info(
            f"[{company_number}] Done — {len(seen)} companies, "
            f"total net assets £{total_net_assets:,}"
        )

    except Exception:
        logger.exception(f"[{company_number}] Fetch failed")
        _fetch_status[company_number] = "error"
