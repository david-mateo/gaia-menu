#!/usr/bin/env python3
"""Build the enrichment request for one parsed menu.

Usage: prepare_enrichment.py <menu.json> [-o request.json] [--glossary data/glossary.json]

Output JSON:
{
  "base_groups": [...],        # tags for the starch/vegetable half
  "protein_groups": [...],     # tags for the protein half
  "lunch_only_groups": [...],  # taggable on a lunch, never suggested for dinner
  "known_translations": {"<ca phrase>": "<en phrase>", ...},
  "new_phrases": ["<ca phrase the glossary does not cover>", ...],
  "days": [{"date": "...", "items": [...], "dessert": "..."}]
}

SKILL.md "Enrich" covers what to write back. The dinner pairing is
computed from the lunch_groups in that response, so this request carries
the tag vocabulary rather than any dinner wording.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import food_groups  # noqa: E402
from food_groups import BASE_GROUPS, LUNCH_ONLY_GROUPS, PROTEIN_GROUPS  # noqa: E402
from models import Menu  # noqa: E402

DEFAULT_GLOSSARY = Path(__file__).parent.parent / "data" / "glossary.json"


def load_glossary(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def menu_phrases(menu: Menu) -> set[str]:
    """Every distinct Catalan phrase the month prints."""
    phrases = {item for day in menu.days for item in day.items}
    phrases |= {day.dessert for day in menu.days if day.dessert}
    return phrases


def build_request(menu: Menu, glossary: dict[str, str]) -> dict[str, Any]:
    phrases = menu_phrases(menu)
    return {
        "base_groups": food_groups.names(BASE_GROUPS),
        "protein_groups": food_groups.names(PROTEIN_GROUPS),
        "lunch_only_groups": food_groups.names(LUNCH_ONLY_GROUPS),
        "known_translations": {p: glossary[p] for p in phrases if p in glossary},
        "new_phrases": sorted(p for p in phrases if p not in glossary),
        "days": [
            {"date": day.date.isoformat(), "items": day.items, "dessert": day.dessert}
            for day in menu.days
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("menu_json", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="Write request here (default: stdout)")
    ap.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    args = ap.parse_args()

    menu = Menu.from_dict(json.loads(args.menu_json.read_text(encoding="utf-8")))
    request = build_request(menu, load_glossary(args.glossary))

    out = json.dumps(request, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
