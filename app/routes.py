import asyncio
import json
import logging
import os
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
from .youtubers import YOUTUBERS

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

READONLY = bool(os.getenv("READ_ONLY"))

BASE_DIR = Path(__file__).parent.parent
STATIC_DATA_DIR = BASE_DIR / "data" / "youtubers"

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
templates.env.globals["base_href"] = "/"

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
            {"request": request, "group": group_cfg, "data": cached, "status": "complete", "readonly": READONLY},
        )

    if READONLY:
        return templates.TemplateResponse(
            "group.html",
            {"request": request, "group": group_cfg, "data": None, "status": "no_data", "company_number": company_number, "readonly": READONLY},
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
            "readonly": READONLY,
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
    if READONLY:
        return RedirectResponse(f"/group/{company_number}", status_code=303)
    await cache_delete_prefix(f"group:{company_number}")
    _fetch_status[company_number] = "running"
    background_tasks.add_task(_fetch_group, company_number)
    return RedirectResponse(f"/group/{company_number}", status_code=303)


# ── Address search page ───────────────────────────────────────────────────────

AMELIA_HOUSE = {
    "label": "Amelia House, Worthing (BN11 1RL)",
    "query": "BN11 1RL",
    "description": "Registered office of Carpenter Box accountants — used by many UK YouTuber companies",
}

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _load_static_data(slug: str) -> Optional[dict]:
    """Return pre-built JSON data for a YouTuber, or None if not yet generated."""
    path = STATIC_DATA_DIR / f"{slug}.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        return None


@app.get("/youtubers", response_class=HTMLResponse)
async def youtubers_page(request: Request):
    group_order = []
    seen_groups: set[str] = set()
    ordered_groups: dict[str, list] = {}
    for y in YOUTUBERS:
        g = y["group"]
        entry = {**y, "slug": _slugify(y["name"])}
        if g not in seen_groups:
            group_order.append(g)
            seen_groups.add(g)
            ordered_groups[g] = []
        ordered_groups[g].append(entry)
    return templates.TemplateResponse(
        "youtubers.html",
        {"request": request, "groups": ordered_groups, "total": len(YOUTUBERS)},
    )


@app.get("/youtuber/{slug}", response_class=HTMLResponse)
async def youtuber_page(request: Request, slug: str, background_tasks: BackgroundTasks):
    yt = next((y for y in YOUTUBERS if _slugify(y["name"]) == slug), None)
    if not yt:
        return HTMLResponse("YouTuber not found", status_code=404)

    # Static pre-built file takes precedence — no API key needed at runtime
    static = _load_static_data(slug)
    if static:
        return templates.TemplateResponse(
            "youtuber.html",
            {"request": request, "yt": yt, "data": static, "status": "complete", "slug": slug, "readonly": True},
        )

    # Development fallback: live cache / API
    cache_key = f"youtuber:{slug}"
    cached = await cache_get(cache_key)
    if cached:
        return templates.TemplateResponse(
            "youtuber.html",
            {"request": request, "yt": yt, "data": cached, "status": "complete", "slug": slug, "readonly": READONLY},
        )

    if READONLY:
        return templates.TemplateResponse(
            "youtuber.html",
            {"request": request, "yt": yt, "data": None, "status": "no_data", "slug": slug, "readonly": READONLY},
        )

    status = _fetch_status.get(cache_key, "idle")
    if status == "idle":
        _fetch_status[cache_key] = "running"
        background_tasks.add_task(_fetch_youtuber, slug)

    return templates.TemplateResponse(
        "youtuber.html",
        {
            "request": request,
            "yt": yt,
            "data": None,
            "status": status if status == "error" else "running",
            "slug": slug,
            "readonly": READONLY,
        },
    )


@app.get("/api/youtuber/{slug}/status")
async def youtuber_status(slug: str):
    cached = await cache_get(f"youtuber:{slug}")
    if cached:
        return {"status": "complete"}
    return {"status": _fetch_status.get(f"youtuber:{slug}", "idle")}


@app.post("/youtuber/{slug}/refresh")
async def refresh_youtuber(slug: str, background_tasks: BackgroundTasks):
    if READONLY:
        return RedirectResponse(f"/youtuber/{slug}", status_code=303)
    cache_key = f"youtuber:{slug}"
    await cache_delete_prefix(cache_key)
    _fetch_status[cache_key] = "running"
    background_tasks.add_task(_fetch_youtuber, slug)
    return RedirectResponse(f"/youtuber/{slug}", status_code=303)


@app.get("/address", response_class=HTMLResponse)
async def address_page(request: Request, page: int = 1, q: str = ""):
    query = AMELIA_HOUSE["query"]
    per_page = 100
    start = (page - 1) * per_page

    client = CHClient()
    search_term = f"{query} {q}".strip() if q else query
    data = await client._get(
        "https://api.company-information.service.gov.uk/search/companies",
        params={
            "q": search_term,
            "items_per_page": per_page,
            "start_index": start,
        },
    )
    items = data.get("items", [])
    total = min(data.get("total_results", 0), 10000)  # CH caps at 10k

    # Enrich with cached balance sheet data where available
    for item in items:
        cn = item.get("company_number", "")
        cached_bs = await cache_get(f"bs:{cn}:{item.get('date_of_creation', '')}")
        if not cached_bs:
            # Try without filing date (any cached BS)
            import aiosqlite
            from .cache import DB_PATH
            try:
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        "SELECT value FROM cache WHERE key LIKE ? LIMIT 1",
                        (f"bs:{cn}:%",),
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            import json
                            cached_bs = json.loads(row[0])
            except Exception:
                pass
        item["balance_sheet"] = cached_bs

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse(
        "address.html",
        {
            "request": request,
            "address": AMELIA_HOUSE,
            "items": items,
            "total": total,
            "page": page,
            "total_pages": min(total_pages, 100),  # cap display at 100 pages
            "per_page": per_page,
            "q": q,
        },
    )


# ── Core fetch logic ──────────────────────────────────────────────────────────

async def _process_company(
    appt: dict,
    client: CHClient,
    api_sem: asyncio.Semaphore,
    pdf_sem: asyncio.Semaphore,
) -> dict:
    """Fetch all accounts filings for a single company appointment."""
    at = appt.get("appointed_to", {})
    cn = at.get("company_number", "")
    entry = {
        "number": cn,
        "name": at.get("company_name", ""),
        "status": at.get("company_status", "active"),
        "role": appt.get("officer_role", ""),
        "appointed_on": appt.get("appointed_on", ""),
        "balance_sheet": None,        # latest, used for sorting
        "all_balance_sheets": [],     # full history, newest first
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

            companies = await asyncio.gather(
                *[_process_company(a, client, api_sem, pdf_sem) for a in companies_raw]
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


async def _fetch_youtuber(slug: str):
    cache_key = f"youtuber:{slug}"
    try:
        yt = next((y for y in YOUTUBERS if _slugify(y["name"]) == slug), None)
        if not yt:
            _fetch_status[cache_key] = "error"
            return

        logger.info(f"[youtuber:{slug}] Starting fetch for {yt['name']}")
        client = CHClient()
        api_sem = asyncio.Semaphore(5)
        pdf_sem = asyncio.Semaphore(3)

        # Find this person's officer record within the seed company
        officers = await client.get_officers(str(yt["seed_company"]))
        surname_upper = yt["surname"].upper()
        officer = next(
            (o for o in officers if surname_upper in o.get("name", "").upper()),
            None,
        )
        if not officer:
            logger.warning(f"[youtuber:{slug}] Could not find officer with surname {surname_upper}")
            _fetch_status[cache_key] = "error"
            return

        officer_id = client.extract_officer_id(officer)
        if not officer_id:
            logger.warning(f"[youtuber:{slug}] Could not extract officer ID")
            _fetch_status[cache_key] = "error"
            return

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
        logger.info(f"[youtuber:{slug}] {len(active_appts)} active appointments")

        companies = list(await asyncio.gather(
            *[_process_company(a, client, api_sem, pdf_sem) for a in active_appts]
        ))
        companies.sort(
            key=lambda c: (c.get("balance_sheet") or {}).get("net_assets") or 0,
            reverse=True,
        )

        total_net_assets = sum(
            (c.get("balance_sheet") or {}).get("net_assets") or 0
            for c in companies
        )

        result = {
            "slug": slug,
            "name": yt["name"],
            "real_name": yt["real_name"],
            "group": yt["group"],
            "officer_name": officer.get("name", ""),
            "officer_id": officer_id,
            "companies": companies,
            "total_companies": len(companies),
            "total_net_assets": total_net_assets,
            "fetched_at": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        }

        await cache_set(cache_key, result, ttl=3600)
        _fetch_status[cache_key] = "complete"
        logger.info(
            f"[youtuber:{slug}] Done — {len(companies)} companies, "
            f"total net assets £{total_net_assets:,}"
        )

    except Exception:
        logger.exception(f"[youtuber:{slug}] Fetch failed")
        _fetch_status[cache_key] = "error"
