#!/usr/bin/env python3
"""Merges an enrichment response into parse_menu.py's JSON, assigns each
day's dinner pairing, and updates the translation glossary.

Usage: apply_enrichment.py <menu.json> <response.json> [-o enriched.json]
       [--glossary data/glossary.json] [--archive archive/]

Expected response.json shape:
{
  "new_translations": {"<ca phrase>": "<en phrase>", ...},
  "days": [
    {"date": "...", "en_items": [...], "en_dessert": "..." | null,
     "ca_title": "...", "en_title": "...",
     "lunch_groups": ["<food group>", ...]}
  ]
}

Adds to each day in menu.json:
  "lunch_food_groups": [...]  (= lunch_groups)
  "dinner_food_groups": {"base": "...", "protein": "..."}
  "title":  "🧑‍🍳 <ca_title>"
  "dinner": "🍽️ <Catalan base> + <Catalan protein>"
  "en": {"items": [...], "dessert": "...", "title": "🧑‍🍳 <en_title>",
         "dinner": "🍽️ <base> + <protein>"}

The dinner pairing (base + protein) is not chosen by the model - it's
computed here by dinner_rotation.assign() from each day's lunch_groups.
"dinner_food_groups" records that pick in machine-readable form;
dinner_rotation.derive_state() replays these from the archive.

Raises EnrichmentError (exit code 2) if a day is missing from the
response, 'lunch_groups' is empty, or contains a value outside
food_groups.LUNCH_TAGS.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from dinner_rotation import DEFAULT_ARCHIVE, assign, derive_state  # noqa: E402
from food_groups import FOOD_GROUPS_EN_TO_CA, LUNCH_ONLY_IMPLIES, LUNCH_TAGS_EN_TO_CA  # noqa: E402
from prepare_enrichment import DEFAULT_GLOSSARY, load_glossary  # noqa: E402

LUNCH_EMOJI = "🧑‍🍳 "
DINNER_EMOJI = "🍽️ "


class EnrichmentError(RuntimeError):
    pass


def apply(menu: dict[str, Any], response: dict[str, Any], rotation: dict[str, Any]) -> dict[str, Any]:
    by_date = {d["date"]: d for d in response["days"]}
    days = menu["days"]

    for i, day in enumerate(days):
        resp = by_date.get(day["date"])
        if resp is None:
            raise EnrichmentError(f"{day['date']}: missing from response")

        for key in ("ca_title", "en_title", "en_items", "lunch_groups"):
            if key not in resp:
                raise EnrichmentError(f"{day['date']}: response missing '{key}'")

        if not resp["lunch_groups"]:
            raise EnrichmentError(f"{day['date']}: 'lunch_groups' is empty")
        for group in resp["lunch_groups"]:
            if group not in LUNCH_TAGS_EN_TO_CA:
                raise EnrichmentError(
                    f"{day['date']}: lunch group '{group}' is not one of "
                    f"{list(LUNCH_TAGS_EN_TO_CA)}"
                )

        next_resp = by_date.get(days[i + 1]["date"]) if i + 1 < len(days) else None
        today_and_tomorrow = resp["lunch_groups"] + (next_resp["lunch_groups"] if next_resp else [])
        excluded = {LUNCH_ONLY_IMPLIES.get(g, g) for g in today_and_tomorrow}
        base, protein = assign(rotation, day["date"], excluded)
        ca_dinner = f"{FOOD_GROUPS_EN_TO_CA[base]} + {FOOD_GROUPS_EN_TO_CA[protein]}"
        en_dinner = f"{base} + {protein}"

        day["lunch_food_groups"] = resp["lunch_groups"]
        day["dinner_food_groups"] = {"base": base, "protein": protein}
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
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE,
                     help="Past months to derive the dinner rotation from")
    args = ap.parse_args()

    menu = json.loads(args.menu_json.read_text(encoding="utf-8"))
    response = json.loads(args.response_json.read_text(encoding="utf-8"))
    rotation = derive_state(args.archive)

    try:
        enriched = apply(menu, response, rotation)
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
