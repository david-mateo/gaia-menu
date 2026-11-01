#!/usr/bin/env python3
"""Month detection from hand-written PDF filenames."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from month_detect import detect_month  # noqa: E402
from fetch_menu import discover_basal_urls, url_month  # noqa: E402


class TestDetectMonth(unittest.TestCase):
    def check(self, name, expect, up=(2026, 10)):
        self.assertEqual(detect_month(name, *up), expect, name)

    def test_real_names(self):
        self.check("202610-ESCOLA-GAIA_BASAL-ESCOLAR-MP.pdf", "202610")
        self.check("ESCOLA-GAIA_BASAL-NOVEMBRE.pdf", "202611")
        self.check("202609-BASAL.pdf", "202609", (2026, 9))

    def test_names_short_names_numbers_any_order(self):
        for n in ["BASAL-nov.pdf", "NOV_BASAL.pdf", "Menu_Novembre_BASAL", "BASAL-11.pdf",
                  "11-BASAL", "BASAL_Noviembre", "basal-november", "11_2026_basal",
                  "BASAL-2026-11", "BASAL-NOV-26", "BASAL.11.26", "202611BASAL", "112026-basal"]:
            self.check(n, "202611")

    def test_accents_and_case(self):
        self.check("BASAL-Març.pdf", "202603", (2026, 2))
        self.check("BASAL-MARÇ", "202603", (2026, 2))
        self.check("basal-DESEMBRE", "202612", (2026, 11))

    def test_year_from_upload_date(self):
        self.check("BASAL-GENER.pdf", "202701", (2026, 12))   # December upload, January menu
        self.check("BASAL-DESEMBRE.pdf", "202512", (2026, 1))
        self.check("BASAL-NOVEMBRE-2027", "202711")            # explicit year wins

    def test_no_substring_false_positives(self):
        self.check("BASAL-marinada.pdf", None)
        self.check("BASAL-dessert.pdf", None)
        self.check("ESCOLA-GAIA_BASAL.pdf", None)

    def test_conflicts_are_rejected(self):
        self.check("BASAL-octubre-novembre", None)
        self.check("BASAL-10-11", None)
        self.check("2026-BASAL-2027-11", None)

    def test_dates_not_mistaken_for_months(self):
        self.check("BASAL-2026.pdf", None)
        self.check("BASAL-v3-nov.pdf", "202611")  # word beats stray number


class TestListing(unittest.TestCase):
    def test_latest_by_menu_month_not_filename(self):
        import fetch_menu
        base = "https://www.escolagaia.cat/wp-content/uploads/"
        html = (f'<a href="{base}2026/09/202609-BASAL.pdf">a</a>'
                f'<a href="{base}2026/10/ESCOLA-GAIA_BASAL-NOVEMBRE.pdf">b</a>'
                f'<a href="{base}2026/10/202610-ESCOLA-GAIA_BASAL-ESCOLAR-MP.pdf">c</a>')
        orig = fetch_menu.fetch
        fetch_menu.fetch = lambda url: html.encode()
        try:
            urls = discover_basal_urls()
        finally:
            fetch_menu.fetch = orig
        self.assertEqual([url_month(u) for u in urls], ["202609", "202610", "202611"])


if __name__ == "__main__":
    unittest.main()
