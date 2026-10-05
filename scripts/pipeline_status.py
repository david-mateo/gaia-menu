#!/usr/bin/env python3
"""Report which step of the monthly Gaia menu run comes next.

Usage: pipeline_status.py [--today YYYY-MM-DD] [--month YYYYMM]

Prints a few KEY=VALUE lines, the last one is always NEXT=<step>.
Work files live in ~/.hermes/gaia-menu-work/<YYYYMM>/ (override: GAIA_WORK).

NEXT values:
  WAIT      not inside the check window (28th..5th) or PDF not published yet. Stop, say nothing.
  FETCH     PDF is published, nothing done yet      -> step 1
  ENRICH    menu.json exists, response.json missing -> step 2-3
  APPLY     response.json exists, enriched.json missing -> step 4
  PUBLISH   enriched.json exists, not yet published -> step 5
  DONE      already published. Stop.
"""
import argparse, datetime, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
WORK = Path(os.environ.get("GAIA_WORK", Path.home() / ".hermes" / "gaia-menu-work"))


def target_month(today: datetime.date):
    """28th..31st -> next month. 1st..5th -> this month. Otherwise None."""
    if today.day >= 28:
        y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return f"{y:04d}{m:02d}"
    if today.day <= 5:
        return f"{today.year:04d}{today.month:02d}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today", help="Override today's date (testing)")
    ap.add_argument("--month", help="Force target month YYYYMM (skips window check)")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    month = a.month or target_month(today)
    if not month:
        print(f"TODAY={today}\nREASON=outside check window (28th-5th)\nNEXT=WAIT")
        return 0
    d = WORK / month
    print(f"TODAY={today}\nMONTH={month}\nWORKDIR={d}")

    if (d / "published.done").exists():
        print("NEXT=DONE"); return 0
    if not (d / "menu.json").exists():
        from fetch_menu import discover_basal_url
        try:
            url = discover_basal_url()
        except Exception as e:  # network or page changed
            print(f"REASON=cannot check listing page: {e}\nNEXT=WAIT"); return 0
        name = url.rsplit("/", 1)[-1]
        if not name.startswith(month):
            print(f"LATEST_PDF={name}\nREASON=menu for {month} not published yet\nNEXT=WAIT")
            return 0
        print(f"PDF_URL={url}\nNEXT=FETCH"); return 0
    for fname, nxt in (("response.json", "ENRICH"), ("enriched.json", "APPLY")):
        if not (d / fname).exists():
            print(f"NEXT={nxt}"); return 0
    print("NEXT=PUBLISH"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
