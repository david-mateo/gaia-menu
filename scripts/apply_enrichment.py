#!/usr/bin/env python3
"""Merges an enrichment response into parse_menu.py's JSON, and updates
the translation glossary.

Usage: apply_enrichment.py <menu.json> <response.json> [-o enriched.json] [--glossary data/glossary.json]

Expected response.json shape:
{
  "new_translations": {"<ca phrase>": "<en phrase>", ...},
  "days": [
    {"date": "...", "en_items": [...], "en_dessert": "..." | null,
     "ca_title": "...", "en_title": "...",
     "dinner_a": "<food group>", "dinner_b": "<food group>"}
  ]
}

Adds to each day in menu.json:
  "title":  "🧑‍🍳 <ca_title>"
  "dinner": "🍽️ <Catalan dinner_a> + <Catalan dinner_b>"
  "en": {"items": [...], "dessert": "...", "title": "🧑‍🍳 <en_title>",
         "dinner": "🍽️ <dinner_a> + <dinner_b>"}

Raises EnrichmentError (exit code 2) if a day is missing from the
response or a dinner pick isn't one of food_groups.FOOD_GROUPS.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from food_groups import FOOD_GROUPS_EN_TO_CA  # noqa: E402
from prepare_enrichment import DEFAULT_GLOSSARY, load_glossary  # noqa: E402

LUNCH_EMOJI = "🧑‍🍳 "
DINNER_EMOJI = "🍽️ "


class EnrichmentError(RuntimeError):
    pass


def apply(menu: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    by_date = {d["date"]: d for d in response["days"]}

    for day in menu["days"]:
        resp = by_date.get(day["date"])
        if resp is None:
            raise EnrichmentError(f"{day['date']}: missing from response")

        for key in ("ca_title", "en_title", "dinner_a", "dinner_b", "en_items"):
            if key not in resp:
                raise EnrichmentError(f"{day['date']}: response missing '{key}'")

        for pick in (resp["dinner_a"], resp["dinner_b"]):
            if pick not in FOOD_GROUPS_EN_TO_CA:
                raise EnrichmentError(
                    f"{day['date']}: dinner pick '{pick}' is not one of "
                    f"{list(FOOD_GROUPS_EN_TO_CA)}"
                )

        ca_dinner = f"{FOOD_GROUPS_EN_TO_CA[resp['dinner_a']]} + {FOOD_GROUPS_EN_TO_CA[resp['dinner_b']]}"
        en_dinner = f"{resp['dinner_a']} + {resp['dinner_b']}"

        day["title"] = LUNCH_EMOJI + resp["ca_title"]
        day["dinner"] = DINNER_EMOJI + ca_dinner
        day["en"] = {
            "items": resp["en_items"],
            "dessert": resp.get("en_dessert"),
            "title": LUNCH_EMOJI + resp["en_title"],
            "dinner": DINNER_EMOJI + en_dinner,
        }
    return menu


def update_glossary(
    glossary_path: Path, glossary: dict[str, str], new_translations: dict[str, str]
) -> None:
    glossary.update(new_translations)
    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.write_text(
        json.dumps(glossary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("menu_json", type=Path)
    ap.add_argument("response_json", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="Write enriched JSON here (default: stdout)")
    ap.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    args = ap.parse_args()

    menu = json.loads(args.menu_json.read_text(encoding="utf-8"))
    response = json.loads(args.response_json.read_text(encoding="utf-8"))

    try:
        enriched = apply(menu, response)
    except EnrichmentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    glossary = load_glossary(args.glossary)
    update_glossary(args.glossary, glossary, response.get("new_translations", {}))

    out = json.dumps(enriched, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
