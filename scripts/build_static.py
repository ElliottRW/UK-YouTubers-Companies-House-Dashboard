#!/usr/bin/env python3
"""
Pre-render all pages to static HTML in docs/ for GitHub Pages.

Usage:
    python scripts/build_static.py

Then commit docs/ and enable GitHub Pages in repo Settings:
  Source: Deploy from branch → main → /docs

The base href is set to match the repo name so all links work under
the /UK-YouTubers-Companies-House-Dashboard/ sub-path on GitHub Pages.
"""

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data" / "youtubers"
OUTPUT_DIR = BASE_DIR / "docs"

# Must match the GitHub repo name exactly
REPO_NAME = "UK-YouTubers-Companies-House-Dashboard"
BASE_HREF = f"/{REPO_NAME}/"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build_jinja_env():
    from app.routes import _fmt_currency, _fmt_name, _fmt_company
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    env.filters["currency"] = _fmt_currency
    env.filters["format_name"] = _fmt_name
    env.filters["company_name"] = _fmt_company
    env.globals["base_href"] = BASE_HREF
    return env


def render(env, template_name, output_path, **ctx):
    tpl = env.get_template(template_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tpl.render(**ctx), encoding="utf-8")


def main():
    from app.youtubers import YOUTUBERS
    from app.config import load_groups

    # Build grouped directory structure
    # Load all JSON data files
    youtuber_data = {}
    for y in YOUTUBERS:
        slug = _slugify(y["name"])
        path = DATA_DIR / f"{slug}.json"
        if path.exists():
            youtuber_data[slug] = json.loads(path.read_text())

    group_order, seen, ordered_groups = [], set(), {}
    for y in YOUTUBERS:
        g = y["group"]
        slug = _slugify(y["name"])
        entry = {
            **y,
            "slug": slug,
            "total_net_assets": youtuber_data.get(slug, {}).get("total_net_assets"),
        }
        if g not in seen:
            group_order.append(g)
            seen.add(g)
            ordered_groups[g] = []
        ordered_groups[g].append(entry)

    # Wipe and recreate docs/
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    # Copy static assets
    static_src = BASE_DIR / "static"
    if static_src.exists() and any(static_src.iterdir()):
        shutil.copytree(static_src, OUTPUT_DIR / "static")

    env = build_jinja_env()

    # Home page — redirect to youtubers directory
    (OUTPUT_DIR / "index.html").write_text(
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        f'<meta http-equiv="refresh" content="0; url=youtubers/">'
        f'<link rel="canonical" href="youtubers/"></head><body></body></html>',
        encoding="utf-8",
    )
    print("  index.html  (redirect → youtubers/)")

    # YouTubers directory
    render(env, "youtubers.html", OUTPUT_DIR / "youtubers" / "index.html",
           groups=ordered_groups, total=len(YOUTUBERS))
    print("  youtubers/index.html")

    # Individual YouTuber pages
    ok = missing = 0
    for y in YOUTUBERS:
        slug = _slugify(y["name"])
        data = youtuber_data.get(slug)
        if not data:
            print(f"  SKIP {y['name']} — run fetch_all.py first")
            missing += 1
            continue
        render(env, "youtuber.html",
               OUTPUT_DIR / "youtuber" / slug / "index.html",
               yt=y, data=data, status="complete", slug=slug, readonly=True)
        ok += 1

    # GitHub Pages needs a .nojekyll file or it strips underscore folders
    (OUTPUT_DIR / ".nojekyll").touch()

    print(f"\n✓ {ok} YouTuber pages built  ({missing} missing data)")
    print(f"  Output: {OUTPUT_DIR}/")
    print(f"\nNext steps:")
    print(f"  git add docs/")
    print(f"  git commit -m 'Build static site'")
    print(f"  git push")
    print(f"  Then: GitHub repo → Settings → Pages → Source: main /docs")


if __name__ == "__main__":
    main()
