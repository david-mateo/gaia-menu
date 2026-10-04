#!/usr/bin/env python3
"""Builds an enrichment request from parse_menu.py's JSON output.

Usage: prepare_enrichment.py <menu.json> [-o request.json] [--glossary data/glossary.json]

Output JSON:
{
  "base_groups": [...English base-course tags you may use...],
  "protein_groups": [...English protein tags you may use...],
  "lunch_only_groups": [...extra tags valid only for lunch_groups,
                         never a dinner suggestion...],
  "known_translations": {"<ca phrase>": "<en phrase>", ...},
  "new_phrases": ["<ca phrase not yet in the glossary>", ...],
  "days": [
    {"date": "...", "items": [...], "dessert": "..."}
  ]
}

See SKILL.md for what to do with this file (an agent fills in a response,
scripts/apply_enrichment.py merges it back). The dinner pairing itself
is computed deterministically from the "lunch_groups" tags you provide
per day (see dinner_rotation.py) - you don't pick it.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from food_groups import BASE_GROUPS, LUNCH_ONLY_GROUPS, PROTEIN_GROUPS  # noqa: E402

DEFAULT_GLOSSARY = Path(__file__).parent.parent / "data" / "glossary.json"


def load_glossary(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def build_request(menu: dict[str, Any], glossary: dict[str, str]) -> dict[str, Any]:
    days = menu["days"]
    phrases: set[str] = set()
    for day in days:
        phrases.update(day["items"])
        if day["dessert"]:
            phrases.add(day["dessert"])

    known = {p: glossary[p] for p in phrases if p in glossary}
    new_phrases = sorted(p for p in phrases if p not in glossary)

    days_ctx: list[dict[str, Any]] = [
        {"date": day["date"], "items": day["items"], "dessert": day["dessert"]}
        for day in days
    ]

    return {
        "base_groups": BASE_GROUPS,
        "protein_groups": PROTEIN_GROUPS,
        "lunch_only_groups": LUNCH_ONLY_GROUPS,
        "known_translations": known,
        "new_phrases": new_phrases,
        "days": days_ctx,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("menu_json", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="Write request here (default: stdout)")
    ap.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    args = ap.parse_args()

    menu = json.loads(args.menu_json.read_text(encoding="utf-8"))
    glossary = load_glossary(args.glossary)
    request = build_request(menu, glossary)

    out = json.dumps(request, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
