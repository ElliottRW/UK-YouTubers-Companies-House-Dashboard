import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "data" / "groups.json"

DEFAULT_GROUPS = [
    {
        "company_number": "12129201",
        "display_name": "The Sidemen",
        "added_at": "2024-01-01T00:00:00",
    }
]


def load_groups() -> list[dict]:
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_GROUPS, indent=2))
        return DEFAULT_GROUPS
    return json.loads(CONFIG_PATH.read_text())


def _save(groups: list[dict]):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(groups, indent=2))


def add_group(company_number: str, display_name: str) -> bool:
    groups = load_groups()
    if any(g["company_number"] == company_number for g in groups):
        return False
    groups.append(
        {
            "company_number": company_number,
            "display_name": display_name,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save(groups)
    return True


def remove_group(company_number: str) -> bool:
    groups = load_groups()
    new = [g for g in groups if g["company_number"] != company_number]
    if len(new) == len(groups):
        return False
    _save(new)
    return True
