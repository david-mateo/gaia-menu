#!/usr/bin/env python3
"""Unit tests for the non-parsing logic: the dinner rotation and the
.ics UID upsert. Run via `python3 scripts/run_tests.py` (which also runs
the golden-file parser checks) or `python3 -m unittest discover tests`.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from dinner_rotation import assign, derive_state, empty_state  # noqa: E402
from food_groups import BASE_GROUPS, PROTEIN_GROUPS, WEIGHTS  # noqa: E402
from publish_ics import parse_existing_events, upsert_one, wrap_vcalendar  # noqa: E402

DTSTAMP = "20261004T000000Z"


def write_archive(root: Path, month: str, days: list[dict]) -> None:
    d = root / month
    d.mkdir(parents=True, exist_ok=True)
    (d / "enriched.json").write_text(json.dumps({"days": days}), encoding="utf-8")


def day(date: str, base: str, protein: str) -> dict:
    return {"date": date, "dinner_food_groups": {"base": base, "protein": protein}}


class TestRotation(unittest.TestCase):
    def test_excluded_groups_are_not_picked(self):
        state = empty_state()
        base, protein = assign(state, "2026-11-02", {"Soup", "Legumes"})
        self.assertNotIn(base, {"Soup", "Legumes"})
        self.assertNotIn(protein, {"Soup", "Legumes"})

    def test_same_date_is_idempotent(self):
        state = empty_state()
        first = assign(state, "2026-11-02", set())
        # a different exclusion set must not change an already-assigned day
        self.assertEqual(assign(state, "2026-11-02", {first[0], first[1]}), first)

    def test_weighting_favours_higher_weight_groups(self):
        state = empty_state()
        for i in range(1, 200):
            assign(state, f"2026-11-{i:03d}", set())
        counts = {g: state["usage"]["protein"][g]["count"] for g in PROTEIN_GROUPS}
        # "Oily Fish" (weight 2) should be picked ~2x as often as "Meat" (weight 1)
        self.assertEqual(WEIGHTS["Oily Fish"], 2)
        self.assertEqual(WEIGHTS["Meat"], 1)
        self.assertAlmostEqual(counts["Oily Fish"] / counts["Meat"], 2.0, delta=0.25)

    def test_every_group_gets_used(self):
        state = empty_state()
        for i in range(1, 60):
            assign(state, f"2026-11-{i:03d}", set())
        for role, groups in (("base", BASE_GROUPS), ("protein", PROTEIN_GROUPS)):
            for g in groups:
                self.assertGreater(state["usage"][role][g]["count"], 0, f"{role}/{g} never used")

    def test_derive_state_replays_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root, "202609", [day("2026-09-01", "Soup", "Legumes")])
            write_archive(root, "202610", [day("2026-10-01", "Soup", "Meat")])
            state = derive_state(root)
            self.assertEqual(state["usage"]["base"]["Soup"]["count"], 2)
            self.assertEqual(state["usage"]["base"]["Soup"]["last_date"], "2026-10-01")
            self.assertEqual(state["usage"]["protein"]["Legumes"]["count"], 1)
            # an archived day keeps its original pairing when re-assigned
            self.assertEqual(assign(state, "2026-09-01", set()), ("Soup", "Legumes"))

    def test_derive_state_skips_retired_vocabulary(self):
        """A category removed from food_groups.py must not crash or count."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root, "202610", [
                day("2026-10-01", "Bread", "Meat"),      # "Bread" was retired
                day("2026-10-02", "Soup", "Legumes"),
            ])
            state = derive_state(root)
            self.assertNotIn("Bread", state["usage"]["base"])
            self.assertNotIn("2026-10-01", state["by_date"])
            self.assertEqual(state["usage"]["base"]["Soup"]["count"], 1)
            # the retired day re-assigns cleanly instead of raising KeyError
            base, _ = assign(state, "2026-10-01", set())
            self.assertIn(base, BASE_GROUPS)

    def test_derive_state_ignores_days_without_structured_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root, "202610", [{"date": "2026-10-01"}])  # pre-schema day
            self.assertEqual(derive_state(root)["by_date"], {})

    def test_derive_state_on_missing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(derive_state(Path(tmp) / "nope")["by_date"], {})


class TestPublishUpsert(unittest.TestCase):
    def menu(self, date: str, title: str) -> dict:
        return {"days": [{
            "date": date, "items": ["x"], "dessert": None, "allergens": None,
            "title": title, "dinner": "🍽️ Sopa + Llegums",
            "en": {"items": ["x"], "dessert": None, "title": title,
                   "dinner": "🍽️ Soup + Legumes"},
        }]}

    def test_upsert_adds_then_updates_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lunch_ca.ics"
            self.assertEqual(upsert_one(self.menu("2026-10-01", "A"), "lunch", "ca", path, DTSTAMP), 1)
            # same date again: replaced, not duplicated
            self.assertEqual(upsert_one(self.menu("2026-10-01", "B"), "lunch", "ca", path, DTSTAMP), 1)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN:VEVENT"), 1)
            self.assertIn("SUMMARY:B", text)
            self.assertNotIn("SUMMARY:A", text)

    def test_upsert_preserves_earlier_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lunch_ca.ics"
            upsert_one(self.menu("2026-09-30", "Sept"), "lunch", "ca", path, DTSTAMP)
            upsert_one(self.menu("2026-10-01", "Oct"), "lunch", "ca", path, DTSTAMP)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN:VEVENT"), 2)
            self.assertIn("SUMMARY:Sept", text)
            self.assertIn("SUMMARY:Oct", text)

    def test_events_are_sorted_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lunch_ca.ics"
            upsert_one(self.menu("2026-10-30", "Late"), "lunch", "ca", path, DTSTAMP)
            upsert_one(self.menu("2026-10-01", "Early"), "lunch", "ca", path, DTSTAMP)
            text = path.read_text(encoding="utf-8")
            self.assertLess(text.index("SUMMARY:Early"), text.index("SUMMARY:Late"))

    def test_output_is_a_single_wellformed_vcalendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lunch_ca.ics"
            upsert_one(self.menu("2026-10-01", "A"), "lunch", "ca", path, DTSTAMP)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN:VCALENDAR"), 1)
            self.assertEqual(text.count("END:VCALENDAR"), 1)
            self.assertTrue(text.startswith("BEGIN:VCALENDAR"))
            self.assertTrue(text.rstrip().endswith("END:VCALENDAR"))

    def test_every_line_ends_crlf_including_preserved_events(self):
        """RFC 5545 requires CRLF. Events re-read from an existing file
        must not come back with the bare LF that read_text() leaves."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lunch_ca.ics"
            upsert_one(self.menu("2026-09-30", "Sept"), "lunch", "ca", path, DTSTAMP)
            upsert_one(self.menu("2026-10-01", "Oct"), "lunch", "ca", path, DTSTAMP)
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n") - raw.count(b"\r\n"), 0, "bare LF found")

    def test_unenriched_days_are_skipped_not_errors(self):
        """A dinner calendar built before enrichment yields zero events."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dinner_ca.ics"
            plain = {"days": [{"date": "2026-10-01", "items": ["x"],
                               "dessert": None, "allergens": None}]}
            self.assertEqual(upsert_one(plain, "dinner", "ca", path, DTSTAMP), 0)

    def test_roundtrip_through_parse_existing_events(self):
        block = ("BEGIN:VEVENT\r\nUID:20261001-lunch@gaia-menu\r\n"
                 "DTSTART:20261001T111500Z\r\nSUMMARY:x\r\nEND:VEVENT")
        text = wrap_vcalendar({"20261001-lunch@gaia-menu": block})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.ics"
            path.write_text(text, encoding="utf-8", newline="")
            self.assertEqual(list(parse_existing_events(path)), ["20261001-lunch@gaia-menu"])


if __name__ == "__main__":
    unittest.main()
