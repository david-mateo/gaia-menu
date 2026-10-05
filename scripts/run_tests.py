#!/usr/bin/env python3
"""Run every test. Golden-file checks for parse_menu.py over
tests/fixtures/*.pdf, then the unit tests in tests/test_units.py.

Usage:
    python3 scripts/run_tests.py                 # run everything
    python3 scripts/run_tests.py --update-golden  # accept current output as golden

Each fixture runs through parse_menu(), then the structural invariants
that hold for any month, then a diff against tests/golden/<stem>.json
when one exists. A fixture with no golden file writes
tests/golden/<stem>.proposed.json rather than failing.

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
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from models import Menu  # noqa: E402
from parse_menu import CATALAN_WEEKDAYS, MenuParseError, parse_menu  # noqa: E402

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"
GOLDEN_DIR = ROOT / "tests" / "golden"


def check_structural_invariants(menu: Menu) -> list[str]:
    """What must hold for any month, independent of a golden file."""
    problems: list[str] = []
    if not menu.days:
        problems.append("zero days parsed")
    for day in menu.days:
        where = day.date.isoformat()
        if (day.date.year, day.date.month) != (menu.year, menu.month):
            problems.append(f"{where}: outside the document's {menu.year}/{menu.month}")
        weekday = day.date.isoweekday()  # 1 = Monday
        if weekday > 5:
            problems.append(f"{where}: falls on a weekend (isoweekday={weekday})")
        elif CATALAN_WEEKDAYS[weekday - 1] != day.weekday:
            problems.append(
                f"{where}: weekday field '{day.weekday}' is not the calendar's "
                f"'{CATALAN_WEEKDAYS[weekday - 1]}'"
            )
        if day.date_label_mismatch:
            problems.append(f"{where}: the PDF labelled this DIA {day.day_label_from_pdf}")
        if not day.items and day.dessert is None:
            problems.append(f"{where}: has no menu but was not filtered out")
    dates = [day.date for day in menu.days]
    if len(dates) != len(set(dates)):
        problems.append("duplicate dates in output")
    return problems


def dump(menu: Menu) -> str:
    return json.dumps(menu.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def run_one(pdf_path: Path, update_golden: bool) -> bool:
    name = pdf_path.stem
    golden_path = GOLDEN_DIR / f"{name}.json"
    proposed_path = GOLDEN_DIR / f"{name}.proposed.json"

    print(f"=== {pdf_path.name} ===")
    try:
        menu = parse_menu(pdf_path)
    except MenuParseError as e:
        print(f"  FAIL: parser raised MenuParseError: {e}")
        return False

    problems = check_structural_invariants(menu)
    if problems:
        print(f"  FAIL: structural invariant violations:")
        for p in problems:
            print(f"    - {p}")
        return False

    actual = dump(menu)

    if update_golden:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual, encoding="utf-8")
        proposed_path.unlink(missing_ok=True)
        print(f"  UPDATED golden ({len(menu.days)} days)")
        return True

    if not golden_path.exists():
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        proposed_path.write_text(actual, encoding="utf-8")
        print(f"  NEW: no golden file yet. Structural checks passed "
              f"({len(menu.days)} days). Proposed output written to:")
        print(f"    {proposed_path.relative_to(ROOT)}")
        print(f"  Review it against the PDF, then run with --update-golden to accept.")
        return True

    expected = golden_path.read_text(encoding="utf-8")
    if actual == expected:
        print(f"  PASS ({len(menu.days)} days)")
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

    print("\n=== unit tests ===")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    units_ok = unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()

    return 0 if all(results) and units_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
