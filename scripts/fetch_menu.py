#!/usr/bin/env python3
"""Download the current month's BASAL menu PDF from Escola Gaia's
families/AFA page.

Usage: fetch_menu.py [--output-dir DIR] [--url URL] [--print-url-only]

Scans the listing page for an <a href> under uploads/<year>/<month>/
whose filename contains "_BASAL" (the school also publishes HALAL,
SENSE-GLUTEN, and other diet variants from the same page).
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

LISTING_URL = "https://www.escolagaia.cat/espai-per-a-les-families-serveis-de-lafa/"
USER_AGENT = "Mozilla/5.0 (gaia-menu-fetcher)"

PDF_LINK_RE = re.compile(
    r'https://www\.escolagaia\.cat/wp-content/uploads/\d{4}/\d{2}/[^"\'<>\s]*_BASAL[^"\'<>\s]*\.pdf',
    re.IGNORECASE,
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def discover_basal_url(listing_url: str = LISTING_URL) -> str:
    html = fetch(listing_url).decode("utf-8", errors="replace")
    matches = sorted(set(PDF_LINK_RE.findall(html)))
    if not matches:
        raise RuntimeError(
            f"No BASAL menu PDF link found on {listing_url}. "
            "The page layout or filename convention may have changed."
        )
    if len(matches) > 1:
        matches.sort(key=_uploads_year_month)  # most recent by year/month last
    return matches[-1]


def _uploads_year_month(url: str) -> tuple[str, str]:
    m = re.search(r"uploads/(\d{4})/(\d{2})/", url)
    assert m is not None  # guaranteed by PDF_LINK_RE
    return m.group(1), m.group(2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--listing-url", default=LISTING_URL,
                     help="Families/AFA services page to scan for the PDF link")
    ap.add_argument("--url", help="Skip discovery and download this PDF URL directly")
    ap.add_argument("--output-dir", default="output", help="Where to save the PDF")
    ap.add_argument("--print-url-only", action="store_true",
                     help="Just print the discovered URL, don't download")
    args = ap.parse_args()

    url = args.url or discover_basal_url(args.listing_url)

    if args.print_url_only:
        print(url)
        return 0

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    dest = out_dir / filename

    print(f"Downloading {url}", file=sys.stderr)
    data = fetch(url)
    dest.write_bytes(data)
    print(str(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
