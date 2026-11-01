#!/usr/bin/env python3
"""Download the current month's BASAL menu PDF from Escola Gaia's
families/AFA page.

Usage: fetch_menu.py [--output-dir DIR] [--url URL] [--print-url-only]

Scans the listing page for an <a href> under uploads/<year>/<month>/
whose filename contains the word "BASAL" (the school also publishes HALAL,
SENSE-GLUTEN, and other diet variants from the same page).
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from month_detect import detect_month  # noqa: E402

LISTING_URL = "https://www.escolagaia.cat/espai-per-a-les-families-serveis-de-lafa/"
USER_AGENT = "Mozilla/5.0 (gaia-menu-fetcher)"

PDF_LINK_RE = re.compile(
    r'https://www\.escolagaia\.cat/wp-content/uploads/\d{4}/\d{2}/[^"\'<>\s]*(?<![A-Za-z])BASAL(?![A-Za-z])[^"\'<>\s]*\.pdf',
    re.IGNORECASE,
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def discover_basal_urls(listing_url: str = LISTING_URL) -> list[str]:
    """Every BASAL PDF on the page, oldest menu month first."""
    html = fetch(listing_url).decode("utf-8", errors="replace")
    matches = sorted(set(PDF_LINK_RE.findall(html)))
    if not matches:
        raise RuntimeError(
            f"No BASAL menu PDF link found on {listing_url}. "
            "The page layout or filename convention may have changed."
        )
    return sorted(matches, key=menu_month_key)


def discover_basal_url(listing_url: str = LISTING_URL) -> str:
    return discover_basal_urls(listing_url)[-1]


def url_month(url: str) -> str | None:
    """YYYYMM the PDF is for, from its hand-written filename."""
    year, month = _uploads_year_month(url)
    return detect_month(url.rsplit("/", 1)[-1], int(year), int(month))


def menu_month_key(url: str) -> tuple[str, str]:
    """Sort key: the menu month, or the upload month when the name has none."""
    detected = url_month(url)
    year, month = _uploads_year_month(url)
    return (detected or year + month, url)


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
