#!/usr/bin/env python3
"""Upsert one month into the four published calendars, matching on event UID.

Usage: publish_ics.py <menu.json> [--public-dir public] [--dtstamp TIMESTAMP]

Writes public/lunch_ca.ics, lunch_en.ics, dinner_ca.ics and dinner_en.ics.
Only the events whose UID the month covers are replaced; every other
event in each file is kept, so earlier months accumulate. Commit and push
public/ afterwards, which SKILL.md covers.

A menu with no enrichment still fills lunch_ca.ics with fallback titles;
the other three come out empty.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from models import Menu  # noqa: E402
from to_ics import Language, MealKind, build_event, utc_now_stamp  # noqa: E402

VEVENT_RE = re.compile(r"BEGIN:VEVENT\r?\n.*?END:VEVENT\r?\n?", re.DOTALL)
UID_RE = re.compile(r"^UID:(.+)$", re.MULTILINE)
DTSTART_RE = re.compile(r"^DTSTART[^:]*:(\d{8})", re.MULTILINE)
LAST_DATE = "99999999"


@dataclass(frozen=True, slots=True)
class Calendar:
    """One published file and the view of the menu it renders."""

    kind: MealKind
    lang: Language

    @property
    def filename(self) -> str:
        return f"{self.kind.value}_{self.lang.value}.ics"


CALENDARS = (
    Calendar(MealKind.LUNCH, Language.CA),
    Calendar(MealKind.LUNCH, Language.EN),
    Calendar(MealKind.DINNER, Language.CA),
    Calendar(MealKind.DINNER, Language.EN),
)


def parse_existing_events(path: Path) -> dict[str, str]:
    """The VEVENT blocks already in `path`, keyed by UID."""
    if not path.exists():
        return {}
    events = {}
    for block in VEVENT_RE.findall(path.read_text(encoding="utf-8")):
        uid = UID_RE.search(block)
        if uid:
            # read_text() turned the CRLF endings into LF; RFC 5545 wants
            # them back.
            events[uid.group(1).strip()] = "\r\n".join(block.rstrip("\r\n").splitlines())
    return events


def wrap_vcalendar(events_by_uid: dict[str, str]) -> str:
    def starts_on(block: str) -> str:
        found = DTSTART_RE.search(block)
        return found.group(1) if found else LAST_DATE

    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//gaia-menu//publish_ics//CA",
        "CALSCALE:GREGORIAN",
        *sorted(events_by_uid.values(), key=starts_on),
        "END:VCALENDAR",
    ]) + "\r\n"


def upsert_one(menu: Menu, calendar: Calendar, path: Path, dtstamp: str) -> int:
    """Merges the month into `path`. Returns the file's total event count."""
    events = parse_existing_events(path)
    for day in menu.days:
        block = build_event(day, dtstamp, calendar.lang, calendar.kind)
        if block is None:
            continue
        uid = UID_RE.search(block)
        assert uid is not None
        events[uid.group(1).strip()] = block

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(wrap_vcalendar(events), encoding="utf-8", newline="")
    return len(events)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("menu_json", type=Path)
    ap.add_argument("--public-dir", type=Path, default=Path("public"))
    ap.add_argument("--dtstamp", help="Override DTSTAMP (UTC); defaults to the current time")
    args = ap.parse_args()

    menu = Menu.from_dict(json.loads(args.menu_json.read_text(encoding="utf-8")))
    dtstamp = args.dtstamp or utc_now_stamp()

    for calendar in CALENDARS:
        path = args.public_dir / calendar.filename
        count = upsert_one(menu, calendar, path, dtstamp)
        print(f"{calendar.filename}: {count} events", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
