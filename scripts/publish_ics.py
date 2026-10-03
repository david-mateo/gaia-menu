#!/usr/bin/env python3
"""Upserts one month's menu JSON into the 4 published calendars by event UID.

Usage: publish_ics.py <menu.json> [--public-dir public] [--dtstamp TIMESTAMP]

Writes/updates:
  public/lunch_ca.ics    public/lunch_en.ics
  public/dinner_ca.ics   public/dinner_en.ics

Replaces only the events whose UID matches a day in menu.json; every
other event in each file is left untouched. Commit and push public/
after running this - see SKILL.md.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from to_ics import build_event  # noqa: E402

VEVENT_RE = re.compile(r"BEGIN:VEVENT\r?\n.*?END:VEVENT\r?\n?", re.DOTALL)
UID_RE = re.compile(r"^UID:(.+)$", re.MULTILINE)
DTSTART_RE = re.compile(r"^DTSTART[^:]*:(\d{8})", re.MULTILINE)

CALENDARS = [
    ("lunch", "ca", "lunch_ca.ics"),
    ("lunch", "en", "lunch_en.ics"),
    ("dinner", "ca", "dinner_ca.ics"),
    ("dinner", "en", "dinner_en.ics"),
]


def parse_existing_events(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    events = {}
    for block in VEVENT_RE.findall(path.read_text(encoding="utf-8")):
        m = UID_RE.search(block)
        if m:
            events[m.group(1).strip()] = block.rstrip("\r\n")
    return events


def wrap_vcalendar(events_by_uid: dict[str, str]) -> str:
    def dtstart_key(block: str) -> str:
        m = DTSTART_RE.search(block)
        return m.group(1) if m else "99999999"

    ordered = sorted(events_by_uid.values(), key=dtstart_key)
    body = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//gaia-menu//publish_ics//CA",
        "CALSCALE:GREGORIAN",
        *ordered,
        "END:VCALENDAR",
    ])
    return body + "\r\n"


def upsert_one(data: dict[str, Any], kind: str, lang: str, path: Path, dtstamp: str) -> int:
    events = parse_existing_events(path)
    for day in data["days"]:
        block = build_event(day, dtstamp, lang, kind)
        if block is None:
            continue
        m = UID_RE.search(block)
        assert m is not None
        events[m.group(1).strip()] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(wrap_vcalendar(events), encoding="utf-8", newline="")
    return len(events)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("menu_json", type=Path)
    ap.add_argument("--public-dir", type=Path, default=Path("public"))
    ap.add_argument("--dtstamp", help="Override DTSTAMP (UTC); defaults to current time")
    args = ap.parse_args()

    data = json.loads(args.menu_json.read_text(encoding="utf-8"))
    dtstamp = args.dtstamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for kind, lang, filename in CALENDARS:
        n = upsert_one(data, kind, lang, args.public_dir / filename, dtstamp)
        print(f"{filename}: {n} events", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
