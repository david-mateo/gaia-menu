#!/usr/bin/env python3
"""Converts parse_menu.py's JSON output into a .ics calendar file, one
timed event per day listed in the JSON.

Usage: to_ics.py <json_file> [-o output.ics] [--lang ca|en] [--kind lunch|dinner] [--dtstamp TIMESTAMP]

--kind lunch (default) uses "title" as SUMMARY and items/dessert/allergens
as DESCRIPTION, falling back to "Menú: <first item>" if not enriched;
event runs 13:15-14:00 Europe/Madrid time.
--kind dinner uses the "dinner" field (from apply_enrichment.py) as both;
event runs 19:00-20:00 Europe/Madrid time.
--lang en reads the "en" sub-object. A day missing the data a given
--lang/--kind combination needs (not yet enriched) is skipped, not an
error.

UIDs are "<date>-<kind>@gaia-menu", stable across months (used by
publish_ics.py for upserting).
"""
import argparse
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ICS_FOLD_WIDTH = 73
MADRID_TZ = ZoneInfo("Europe/Madrid")
EVENT_TIMES = {
    "lunch": (time(13, 15), time(14, 0)),
    "dinner": (time(19, 0), time(20, 0)),
}


def to_utc_stamp(date_str: str, local_time: time) -> str:
    local = datetime.combine(date.fromisoformat(date_str), local_time, tzinfo=MADRID_TZ)
    return local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def build_event(day: dict[str, Any], dtstamp: str, lang: str, kind: str = "lunch") -> str | None:
    """Returns one VEVENT block, or None if this day has nothing to show
    for the requested kind (e.g. a dinner calendar before enrichment)."""
    date_compact = day["date"].replace("-", "")
    en: dict[str, Any] = day.get("en", {})

    if kind == "dinner":
        dinner = en.get("dinner") if lang == "en" else day.get("dinner")
        if dinner is None:
            return None
        title = en.get("title") if lang == "en" else day.get("title")
        context_label = "Today's lunch" if lang == "en" else "Dinar d'avui"
        summary = dinner
        description = f"{context_label}: {title}" if title else ""
    else:
        if lang == "en":
            if "en" not in day:
                return None
            items, dessert = en["items"], en["dessert"]
            title = en.get("title")
            dessert_label, allergen_label = "Dessert", "Allergens"
            fallback = f"Lunch: {items[0]}" if items else "School lunch"
        else:
            items, dessert = day["items"], day["dessert"]
            title = day.get("title")
            dessert_label, allergen_label = "Postres", "Al·lèrgens"
            fallback = f"Menú: {items[0]}" if items else "Menú escolar"

        summary = title or fallback
        desc_lines = list(items)
        if dessert:
            desc_lines.append(f"{dessert_label}: {dessert}")
        if day.get("allergens"):
            desc_lines.append(f"{allergen_label}: {', '.join(str(a) for a in day['allergens'])}")
        description = "\n".join(desc_lines)

    start_time, end_time = EVENT_TIMES[kind]
    uid = f"{date_compact}-{kind}@gaia-menu"
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{to_utc_stamp(day['date'], start_time)}",
        f"DTEND:{to_utc_stamp(day['date'], end_time)}",
        f"SUMMARY:{escape_text(summary)}",
        f"DESCRIPTION:{escape_text(description)}",
        "END:VEVENT",
    ]
    return "\r\n".join(fold(l) for l in lines)


def build_ics(data: dict[str, Any], dtstamp: str, lang: str = "ca", kind: str = "lunch") -> str:
    events = [e for e in (build_event(day, dtstamp, lang, kind) for day in data["days"]) if e]
    body = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//gaia-menu//parse_menu//CA",
        "CALSCALE:GREGORIAN",
        *events,
        "END:VCALENDAR",
    ])
    return body + "\r\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json_file", type=Path, help="Output of parse_menu.py")
    ap.add_argument("-o", "--output", type=Path, help="Write .ics here instead of stdout")
    ap.add_argument("--lang", choices=["ca", "en"], default="ca")
    ap.add_argument("--kind", choices=["lunch", "dinner"], default="lunch")
    ap.add_argument("--dtstamp", help="Override DTSTAMP (UTC, e.g. 20261003T000000Z); "
                                       "defaults to current time")
    args = ap.parse_args()

    data = json.loads(args.json_file.read_text(encoding="utf-8"))

    dtstamp = args.dtstamp
    if not dtstamp:
        import datetime
        dtstamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics = build_ics(data, dtstamp, args.lang, args.kind)
    if args.output:
        args.output.write_text(ics, encoding="utf-8", newline="")
    else:
        sys.stdout.write(ics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
