import asyncio
import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.company-information.service.gov.uk"
DOC_API_URL = "https://document-api.company-information.service.gov.uk"


def _auth() -> tuple[str, str]:
    key = os.getenv("CH_API_KEY", "")
    if not key:
        raise ValueError("CH_API_KEY environment variable not set. See .env.example")
    return (key, "")


class CHClient:
    async def _get(self, url: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(auth=_auth(), timeout=30.0) as client:
            for attempt in range(3):
                try:
                    r = await client.get(url, params=params)
                    if r.status_code == 429:
                        await asyncio.sleep(2 ** attempt + 1)
                        continue
                    if r.status_code == 404:
                        return {}
                    r.raise_for_status()
                    return r.json()
                except httpx.HTTPStatusError as e:
                    logger.warning(f"HTTP {e.response.status_code} for {url}")
                    if attempt == 2:
                        return {}
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Request error for {url}: {e}")
                    if attempt == 2:
                        return {}
                    await asyncio.sleep(1)
        return {}

    async def get_company(self, company_number: str) -> dict:
        return await self._get(f"{BASE_URL}/company/{company_number}")

    async def get_officers(self, company_number: str) -> list:
        data = await self._get(
            f"{BASE_URL}/company/{company_number}/officers",
            params={"items_per_page": 100, "register_view": "false"},
        )
        return data.get("items", [])

    def extract_officer_id(self, officer: dict) -> Optional[str]:
        link = officer.get("links", {}).get("officer", {}).get("appointments", "")
        m = re.search(r"/officers/([^/]+)/appointments", link)
        return m.group(1) if m else None

    async def get_appointments(self, officer_id: str) -> list:
        all_items = []
        start = 0
        while True:
            data = await self._get(
                f"{BASE_URL}/officers/{officer_id}/appointments",
                params={"items_per_page": 50, "start_index": start},
            )
            items = data.get("items", [])
            all_items.extend(items)
            total = data.get("total_results", 0)
            if len(all_items) >= total or not items:
                break
            start += 50
        return all_items

    async def get_latest_accounts_filing(self, company_number: str) -> Optional[dict]:
        filings = await self.get_all_accounts_filings(company_number)
        return filings[0] if filings else None

    async def get_all_accounts_filings(self, company_number: str) -> list:
        """Return every accounts filing for a company, most recent first."""
        all_filings = []
        start = 0
        while True:
            data = await self._get(
                f"{BASE_URL}/company/{company_number}/filing-history",
                params={"category": "accounts", "items_per_page": 100, "start_index": start},
            )
            items = data.get("items", [])
            for item in items:
                desc = item.get("description", "").lower()
                type_ = item.get("type", "").lower()
                if any(k in desc for k in ["total exemption", "full accounts", "micro-entity", "micro entity"]):
                    all_filings.append(item)
                elif type_ in ("aa", "aamd", "aa01"):
                    all_filings.append(item)
            if len(items) < 100:
                break
            start += 100
        return all_filings

    async def download_pdf(self, doc_metadata_url: str) -> Optional[bytes]:
        """Download the iXBRL (structured data) version of a filing."""
        try:
            doc_id = doc_metadata_url.rstrip("/").split("/document/")[-1].split("?")[0]

            async with httpx.AsyncClient(
                auth=_auth(), timeout=60.0, follow_redirects=True
            ) as client:
                r = await client.get(
                    f"{DOC_API_URL}/document/{doc_id}/content",
                    headers={"Accept": "application/xhtml+xml"},
                )
                if r.status_code == 200 and _is_ixbrl(r.content):
                    return r.content

                logger.warning(f"Document {doc_id}: no iXBRL available")
                return None
        except Exception as e:
            logger.error(f"Failed to download document {doc_metadata_url}: {e}")
            return None


def _is_ixbrl(content: bytes) -> bool:
    return len(content) > 100 and (
        b"ix:nonFraction" in content or b"nonFraction" in content
    )
