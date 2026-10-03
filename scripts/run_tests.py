#!/usr/bin/env python3
"""Regression runner for parse_menu.py against tests/fixtures/*.pdf.

Usage:
    python3 scripts/run_tests.py                 # check all fixtures
    python3 scripts/run_tests.py --update-golden  # accept current output as golden

For each fixture: runs parse_menu(), checks structural invariants
(weekday matches the date, no date_label_mismatch, no duplicate dates),
then diffs the result against tests/golden/<stem>.json if present. A
fixture with no golden file writes tests/golden/<stem>.proposed.json
instead of failing.

Adding a new month:
  1. cp <pdf> tests/fixtures/<YYYYMM>-BASAL.pdf
  2. python3 scripts/run_tests.py           # writes <stem>.proposed.json
  3. review the proposed JSON against the PDF
  4. python3 scripts/run_tests.py --update-golden
"""
import argparse
import datetime
import difflib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from parse_menu import parse_menu, MenuParseError, CATALAN_WEEKDAYS  # noqa: E402

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"
GOLDEN_DIR = ROOT / "tests" / "golden"


def check_structural_invariants(data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not data["days"]:
        problems.append("zero days parsed")
    for day in data["days"]:
        y, m, d = (int(x) for x in day["date"].split("-"))
        if (y, m) != (data["year"], data["month"]):
            problems.append(f"{day['date']}: year/month doesn't match document ({data['year']}/{data['month']})")
        iso_weekday = datetime.date(y, m, d).isoweekday()  # 1=Monday
        if iso_weekday > 5:
            problems.append(f"{day['date']}: falls on a weekend (isoweekday={iso_weekday})")
        elif CATALAN_WEEKDAYS[iso_weekday - 1] != day["weekday"]:
            problems.append(
                f"{day['date']}: weekday field '{day['weekday']}' != actual "
                f"calendar weekday '{CATALAN_WEEKDAYS[iso_weekday - 1]}'"
            )
        if day["date_label_mismatch"]:
            problems.append(f"{day['date']}: date_label_mismatch is True "
                             f"(PDF said DIA {day['day_label_from_pdf']})")
        if not day["items"] and day["dessert"] is None:
            problems.append(f"{day['date']}: has no menu content but wasn't filtered out")
    dates = [day["date"] for day in data["days"]]
    if len(dates) != len(set(dates)):
        problems.append("duplicate dates in output")
    return problems


def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def run_one(pdf_path: Path, update_golden: bool) -> bool:
    name = pdf_path.stem
    golden_path = GOLDEN_DIR / f"{name}.json"
    proposed_path = GOLDEN_DIR / f"{name}.proposed.json"

    print(f"=== {pdf_path.name} ===")
    try:
        data = parse_menu(pdf_path)
    except MenuParseError as e:
        print(f"  FAIL: parser raised MenuParseError: {e}")
        return False

    problems = check_structural_invariants(data)
    if problems:
        print(f"  FAIL: structural invariant violations:")
        for p in problems:
            print(f"    - {p}")
        return False

    actual = dump(data)

    if update_golden:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual, encoding="utf-8")
        proposed_path.unlink(missing_ok=True)
        print(f"  UPDATED golden ({len(data['days'])} days)")
        return True

    if not golden_path.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        proposed_path.write_text(actual, encoding="utf-8")
        print(f"  NEW: no golden file yet. Structural checks passed "
              f"({len(data['days'])} days). Proposed output written to:")
        print(f"    {proposed_path.relative_to(ROOT)}")
        print(f"  Review it against the PDF, then run with --update-golden to accept.")
        return True

    expected = golden_path.read_text(encoding="utf-8")
    if actual == expected:
        print(f"  PASS ({len(data['days'])} days)")
        return True

    print(f"  FAIL: output differs from {golden_path.relative_to(ROOT)}:")
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True), actual.splitlines(keepends=True),
        fromfile="golden", tofile="actual",
    )
    sys.stdout.writelines(f"    {line}" for line in diff)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update-golden", action="store_true",
                     help="Overwrite golden files with current parser output for all fixtures")
    args = ap.parse_args()

    if not FIXTURES_DIR.exists():
        print(f"No fixtures directory at {FIXTURES_DIR}", file=sys.stderr)
        return 1
    pdfs = sorted(FIXTURES_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF fixtures found in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    results = [run_one(p, args.update_golden) for p in pdfs]
    print()
    print(f"{sum(results)}/{len(results)} fixtures OK")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
