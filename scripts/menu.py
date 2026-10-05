#!/usr/bin/env python3
"""Fetch this month's Gaia BASAL menu PDF, parse it, and print the JSON.
Writes an .ics alongside it on request.

Usage:
    python3 scripts/menu.py                        # JSON to stdout
    python3 scripts/menu.py -o menu.json            # JSON to a file
    python3 scripts/menu.py --ics menu.ics          # also write .ics
    python3 scripts/menu.py --pdf some/local.pdf    # parse a given PDF, skip fetching

Exit codes: 0 ok, 1 fetch failed, 2 MenuParseError (report the message verbatim).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_menu import discover_basal_url, fetch  # noqa: E402
from parse_menu import parse_menu, MenuParseError  # noqa: E402
from to_ics import build_ics, utc_now_stamp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, help="Use this local PDF instead of fetching one")
    ap.add_argument("--download-dir", type=Path, default=Path("output"),
                     help="Where to save a freshly fetched PDF (default: output/)")
    ap.add_argument("-o", "--output", type=Path, help="Write JSON here (default: stdout)")
    ap.add_argument("--ics", type=Path, help="Also write an .ics calendar file here")
    args = ap.parse_args()

    if args.pdf:
        pdf_path = args.pdf
    else:
        try:
            url = discover_basal_url()
            args.download_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = args.download_dir / url.rsplit("/", 1)[-1]
            print(f"Fetching {url}", file=sys.stderr)
            pdf_path.write_bytes(fetch(url))
        except Exception as e:
            print(f"ERROR fetching menu PDF: {e}", file=sys.stderr)
            return 1

    try:
        menu = parse_menu(pdf_path)
    except MenuParseError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_json = json.dumps(menu.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(out_json, encoding="utf-8")
    else:
        print(out_json)

    if args.ics:
        args.ics.write_text(build_ics(menu, utc_now_stamp()), encoding="utf-8", newline="")
        print(f"Wrote {args.ics}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
