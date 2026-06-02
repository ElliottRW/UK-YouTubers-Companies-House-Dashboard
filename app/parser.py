import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def extract_balance_sheet(content: bytes) -> dict:
    """Parse an iXBRL document and return balance sheet figures."""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Decode error: {e}")
        return {}

    if "nonFraction" not in text:
        logger.warning("Document is not iXBRL")
        return {}

    result = {}

    # ── Step 1: parse contexts ────────────────────────────────────────────────
    # contexts: id -> {"date": "YYYY-MM-DD", "instant": bool, "has_dims": bool}
    contexts: dict[str, dict] = {}
    for attrs, body in re.findall(
        r"<xbrli:context\b([^>]*)>(.*?)</xbrli:context>", text, re.DOTALL
    ):
        ctx_id_m = re.search(r'id="([^"]+)"', attrs)
        if not ctx_id_m:
            continue
        ctx_id = ctx_id_m.group(1)
        instant_m = re.search(r"<xbrli:instant>(\d{4}-\d{2}-\d{2})", body)
        end_m = re.search(r"<xbrli:endDate>(\d{4}-\d{2}-\d{2})", body)
        has_dims = bool(re.search(r"explicitMember", body))
        if instant_m:
            contexts[ctx_id] = {"date": instant_m.group(1), "instant": True, "has_dims": has_dims}
        elif end_m:
            contexts[ctx_id] = {"date": end_m.group(1), "instant": False, "has_dims": has_dims}

    # ── Step 2: identify current & prior year balance-sheet contexts ──────────
    # Balance sheet uses instant contexts; prefer non-dimensional ones
    bs_ctxs = {k: v for k, v in contexts.items() if v["instant"] and not v["has_dims"]}
    if not bs_ctxs:
        bs_ctxs = {k: v for k, v in contexts.items() if v["instant"]}
    if not bs_ctxs:
        logger.warning("No instant contexts found in iXBRL")
        return {}

    dates_sorted = sorted({v["date"] for v in bs_ctxs.values()}, reverse=True)
    current_date = dates_sorted[0]
    prior_date = dates_sorted[1] if len(dates_sorted) > 1 else None

    # Base (non-dimensional) contexts — used for summary items like total_equity
    base_curr = {k for k, v in bs_ctxs.items() if v["date"] == current_date}
    base_prior = {k for k, v in bs_ctxs.items() if v["date"] == prior_date} if prior_date else set()

    # All instant contexts for this date — used for line items like creditors
    current_ctx = {k for k, v in contexts.items() if v.get("instant") and v["date"] == current_date}
    prior_ctx = {k for k, v in contexts.items() if v.get("instant") and v["date"] == prior_date} if prior_date else set()

    # ── Step 3: set date metadata ─────────────────────────────────────────────
    try:
        d = datetime.strptime(current_date, "%Y-%m-%d")
        result["date"] = d.strftime("%-d %B %Y")
        result["year"] = d.year
    except ValueError:
        pass
    if prior_date:
        try:
            result["prior_year"] = datetime.strptime(prior_date, "%Y-%m-%d").year
        except ValueError:
            pass

    # ── Step 4: concept → result-key map (ordered: most specific first) ───────
    CONCEPT_MAP = [
        ("totalassetslesscurrentliabilities", "net_assets",          False),
        ("netassetsliabilities",              "net_assets",          False),
        ("netassets",                         "net_assets",          False),
        ("fixedassets",                       "fixed_assets",        False),
        ("totalfixedassets",                  "fixed_assets",        False),
        ("investmentsfixedassets",            "investments",         False),
        ("debtors",                           "debtors",             False),
        ("cashatbankandinhand",               "cash",                False),
        ("creditorsamountsfalling",           "creditors",           True),
        ("creditors",                         "creditors",           True),
        ("netcurrentassetsliabilities",       "net_current_assets",  False),
        ("profitlossaccount",                 "profit_loss_reserves",False),
        ("retainedearnings",                  "profit_loss_reserves",False),
        ("calledupshare",                     "called_up_capital",   False),
        ("issuedcapital",                     "called_up_capital",   False),
        # equity (total) — only used when context has NO dimensions
        ("equity",                            "total_equity",        False),
    ]

    def _map(local_name: str):
        cl = local_name.lower().replace("-", "").replace("_", "")
        for suffix, key, negate in CONCEPT_MAP:
            if cl == suffix or cl.startswith(suffix) or suffix in cl:
                return key, negate
        return None, False

    def _parse_val(value_str: str, attrs: str) -> Optional[int]:
        try:
            val_clean = re.sub(r"[^\d.]", "", value_str.strip())
            if not val_clean:
                return None
            val = float(val_clean)
            scale_m = re.search(r'scale="([-\d]+)"', attrs)
            if scale_m:
                val *= 10 ** int(scale_m.group(1))
            val = int(round(val))
            sign_m = re.search(r'sign="([^"]+)"', attrs)
            if sign_m and sign_m.group(1) == "-":
                val = -val
            return val
        except (ValueError, OverflowError):
            return None

    # ── Step 5: extract nonFraction elements ──────────────────────────────────
    nonfrac_re = re.compile(
        r"<(?:ix:)?nonFraction\s+([^>]*?)>\s*([-\d,. ]+)\s*</(?:ix:)?nonFraction>",
        re.IGNORECASE | re.DOTALL,
    )

    curr_vals: dict[str, int] = {}
    prior_vals: dict[str, int] = {}

    for attrs, value_str in nonfrac_re.findall(text):
        name_m = re.search(r'name="([^"]+)"', attrs)
        ctx_m = re.search(r'contextRef="([^"]+)"', attrs)
        if not name_m or not ctx_m:
            continue

        ctx_ref = ctx_m.group(1)
        is_curr = ctx_ref in current_ctx
        is_prior = ctx_ref in prior_ctx
        if not is_curr and not is_prior:
            continue

        local_name = name_m.group(1).split(":")[-1]
        key, negate = _map(local_name)
        if not key:
            continue

        # For total_equity, only accept base (non-dimensional) contexts
        if key == "total_equity":
            if is_curr and ctx_ref not in base_curr:
                continue
            if is_prior and ctx_ref not in base_prior:
                continue

        val = _parse_val(value_str, attrs)
        if val is None:
            continue
        if negate:
            val = -abs(val)

        if is_curr:
            curr_vals.setdefault(key, val)
        else:
            prior_vals.setdefault(key, val)

    result.update(curr_vals)
    for k, v in prior_vals.items():
        result[f"{k}_prior"] = v

    logger.info(f"iXBRL parsed: {list(result.keys())}")
    return result
