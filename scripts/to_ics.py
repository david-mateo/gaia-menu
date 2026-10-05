#!/usr/bin/env python3
"""Render a parsed or enriched menu as a .ics calendar, one timed event
per day.

Usage: to_ics.py <json_file> [-o output.ics] [--lang ca|en] [--kind lunch|dinner]
                 [--dtstamp TIMESTAMP]

Lunch events run 13:15 to 14:00 and dinner events 19:00 to 20:00, both
Europe/Madrid, converted to UTC so the published file needs no VTIMEZONE.
A lunch event falls back to "Menú: <first item>" when the day has no
enrichment. A day that lacks what the chosen language and meal need is
skipped rather than raising.

UIDs are "<date>-<kind>@gaia-menu", stable across months, which is what
publish_ics.py upserts on.
"""
import argparse
import datetime
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from models import Menu, MenuDay  # noqa: E402

ICS_FOLD_WIDTH = 73
MADRID = ZoneInfo("Europe/Madrid")


class Language(str, Enum):
    CA = "ca"
    EN = "en"


class MealKind(str, Enum):
    LUNCH = "lunch"
    DINNER = "dinner"


@dataclass(frozen=True, slots=True)
class MealTimes:
    start: datetime.time
    end: datetime.time


MEAL_TIMES = {
    MealKind.LUNCH: MealTimes(datetime.time(13, 15), datetime.time(14, 0)),
    MealKind.DINNER: MealTimes(datetime.time(19, 0), datetime.time(20, 0)),
}


@dataclass(frozen=True, slots=True)
class Labels:
    """The fixed wording each language puts around a day's dishes."""

    dessert: str
    allergens: str
    todays_lunch: str
    untitled_lunch: str


LABELS = {
    Language.CA: Labels(dessert="Postres", allergens="Al·lèrgens",
                         todays_lunch="Dinar d'avui", untitled_lunch="Menú escolar"),
    Language.EN: Labels(dessert="Dessert", allergens="Allergens",
                         todays_lunch="Today's lunch", untitled_lunch="School lunch"),
}


def to_utc_stamp(day: datetime.date, local_time: datetime.time) -> str:
    local = datetime.datetime.combine(day, local_time, tzinfo=MADRID)
    return local.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escape_text(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line: str) -> str:
    if len(line) <= ICS_FOLD_WIDTH:
        return line
    parts = [line[:ICS_FOLD_WIDTH]]
    rest = line[ICS_FOLD_WIDTH:]
    while rest:
        parts.append(" " + rest[:ICS_FOLD_WIDTH - 1])
        rest = rest[ICS_FOLD_WIDTH - 1:]
    return "\r\n".join(parts)


def lunch_content(day: MenuDay, lang: Language) -> tuple[str, str] | None:
    """(summary, description) for a lunch event, or None when the day
    lacks a translation the chosen language needs."""
    labels = LABELS[lang]
    if lang is Language.EN:
        if day.enrichment is None:
            return None
        items = list(day.enrichment.items_en)
        dessert = day.enrichment.dessert_en
        summary = day.enrichment.lunch_title_en
    else:
        items = list(day.items)
        dessert = day.dessert
        summary = (day.enrichment.lunch_title_ca if day.enrichment
                    else f"Menú: {items[0]}" if items else labels.untitled_lunch)

    lines = list(items)
    if dessert:
        lines.append(f"{labels.dessert}: {dessert}")
    if day.allergens:
        lines.append(f"{labels.allergens}: {', '.join(str(a) for a in day.allergens)}")
    return summary, "\n".join(lines)


def dinner_content(day: MenuDay, lang: Language) -> tuple[str, str] | None:
    if day.enrichment is None:
        return None
    labels = LABELS[lang]
    if lang is Language.EN:
        summary, lunch_title = day.enrichment.dinner_en, day.enrichment.lunch_title_en
    else:
        summary, lunch_title = day.enrichment.dinner_ca, day.enrichment.lunch_title_ca
    return summary, f"{labels.todays_lunch}: {lunch_title}"


def build_event(day: MenuDay, dtstamp: str, lang: Language,
                 kind: MealKind = MealKind.LUNCH) -> str | None:
    """One VEVENT block, or None when this day has nothing to show for
    the chosen language and meal."""
    content = (dinner_content(day, lang) if kind is MealKind.DINNER
                else lunch_content(day, lang))
    if content is None:
        return None
    summary, description = content

    times = MEAL_TIMES[kind]
    lines = [
        "BEGIN:VEVENT",
        f"UID:{day.compact_date}-{kind.value}@gaia-menu",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{to_utc_stamp(day.date, times.start)}",
        f"DTEND:{to_utc_stamp(day.date, times.end)}",
        f"SUMMARY:{escape_text(summary)}",
        f"DESCRIPTION:{escape_text(description)}",
        "END:VEVENT",
    ]
    return "\r\n".join(fold(line) for line in lines)


def build_ics(menu: Menu, dtstamp: str, lang: Language = Language.CA,
               kind: MealKind = MealKind.LUNCH) -> str:
    events = [e for e in (build_event(day, dtstamp, lang, kind) for day in menu.days) if e]
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//gaia-menu//parse_menu//CA",
        "CALSCALE:GREGORIAN",
        *events,
        "END:VCALENDAR",
    ]) + "\r\n"


def utc_now_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file", type=Path, help="Output of parse_menu.py")
    ap.add_argument("-o", "--output", type=Path, help="Write .ics here instead of stdout")
    ap.add_argument("--lang", type=Language, choices=list(Language), default=Language.CA)
    ap.add_argument("--kind", type=MealKind, choices=list(MealKind), default=MealKind.LUNCH)
    ap.add_argument("--dtstamp", help="Override DTSTAMP (UTC, e.g. 20261003T000000Z); "
                                       "defaults to the current time")
    args = ap.parse_args()

    menu = Menu.from_dict(json.loads(args.json_file.read_text(encoding="utf-8")))
    ics = build_ics(menu, args.dtstamp or utc_now_stamp(), args.lang, args.kind)

    if args.output:
        args.output.write_text(ics, encoding="utf-8", newline="")
    else:
        sys.stdout.write(ics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
