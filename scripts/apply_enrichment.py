#!/usr/bin/env python3
"""Merge an enrichment response into a parsed menu, assign each day's
dinner pairing, and grow the translation glossary.

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

Each day gains lunch_food_groups, dinner_food_groups, title, dinner, and
an "en" block. The model does not choose the dinner pairing:
dinner_rotation assigns it from the lunch tags, and dinner_food_groups
records it for later replay.

Exits 2 with a message naming the day when a day is missing from the
response, its lunch_groups is empty, or it names a group outside the
vocabulary.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import food_groups  # noqa: E402
from dinner_rotation import DEFAULT_ARCHIVE, RotationState, derive_state  # noqa: E402
from models import DayResponse, Enrichment, EnrichmentResponse, Menu, MenuError  # noqa: E402
from prepare_enrichment import DEFAULT_GLOSSARY, load_glossary  # noqa: E402


def excluded_groups(*entries: DayResponse | None) -> set[str]:
    """Group names the given lunches rule out of a dinner pairing."""
    excluded: set[str] = set()
    for entry in entries:
        if entry is None:
            continue
        for group in entry.lunch_groups:
            excluded |= food_groups.excluded_by(group)
    return excluded


def apply(menu: Menu, response: EnrichmentResponse, rotation: RotationState) -> Menu:
    """Fills in every day's Enrichment, in date order so the rotation sees
    each day's pairing before it picks the next."""
    for i, day in enumerate(menu.days):
        entry = response.days.get(day.date)
        if entry is None:
            raise MenuError(f"{day.date.isoformat()}: missing from response")

        # The next school day's lunch is excluded too, so a dinner never
        # repeats what is eaten within a day of it.
        next_day = menu.days[i + 1] if i + 1 < len(menu.days) else None
        next_entry = response.days.get(next_day.date) if next_day else None
        pairing = rotation.assign(day.date, excluded_groups(entry, next_entry))

        day.enrichment = Enrichment(
            lunch_groups=entry.lunch_groups,
            pairing=pairing,
            title_ca=entry.title_ca,
            title_en=entry.title_en,
            items_en=entry.items_en,
            dessert_en=entry.dessert_en,
        )
    return menu


def update_glossary(path: Path, new_translations: dict[str, str]) -> None:
    glossary = load_glossary(path)
    glossary.update(new_translations)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
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

    try:
        menu = Menu.from_dict(json.loads(args.menu_json.read_text(encoding="utf-8")))
        response = EnrichmentResponse.from_dict(
            json.loads(args.response_json.read_text(encoding="utf-8")))
        enriched = apply(menu, response, derive_state(args.archive))
    except MenuError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    update_glossary(args.glossary, response.new_translations)

    out = json.dumps(enriched.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
