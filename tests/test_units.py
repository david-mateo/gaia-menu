#!/usr/bin/env python3
"""Unit tests for the non-parsing logic: the dinner rotation and the .ics
UID upsert. Run via `python3 scripts/run_tests.py`, which also runs the
golden-file parser checks, or `python3 -m unittest discover tests`.
"""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import food_groups  # noqa: E402
from dinner_rotation import RotationState, derive_state  # noqa: E402
from food_groups import BASE_GROUPS, PROTEIN_GROUPS  # noqa: E402
from models import DinnerPairing, Enrichment, Menu, MenuDay  # noqa: E402
from publish_ics import Calendar, parse_existing_events, upsert_one, wrap_vcalendar  # noqa: E402
from to_ics import Language, MealKind  # noqa: E402

DTSTAMP = "20261004T000000Z"
LUNCH_CA = Calendar(MealKind.LUNCH, Language.CA)
DINNER_CA = Calendar(MealKind.DINNER, Language.CA)


def group(name: str):
    found = food_groups.find(name)
    assert found is not None, name
    return found


def pairing(base: str, protein: str) -> DinnerPairing:
    return DinnerPairing(group(base), group(protein))


def day(date: str, title: str = "A", enriched: DinnerPairing | None = None) -> MenuDay:
    menu_day = MenuDay(
        date=datetime.date.fromisoformat(date), weekday="Dilluns", items=["x"],
        dessert=None, allergens=None, day_label_from_pdf=None, date_label_mismatch=False,
    )
    if enriched is not None:
        menu_day.enrichment = Enrichment(
            lunch_groups=(group("Pasta"),), pairing=enriched, title_ca=title,
            title_en=title, items_en=("x",), dessert_en=None,
        )
    return menu_day


def menu(*days: MenuDay) -> Menu:
    return Menu(year=2026, month=10, days=list(days))


def write_archive(root: Path, month: str, days: list[dict]) -> None:
    month_dir = root / month
    month_dir.mkdir(parents=True, exist_ok=True)
    (month_dir / "enriched.json").write_text(
        json.dumps({"year": 2026, "month": int(month[4:]), "days": days}), encoding="utf-8")


class TestRotation(unittest.TestCase):
    def test_excluded_groups_are_not_picked(self):
        state = RotationState()
        chosen = state.assign(datetime.date(2026, 11, 2), {"Soup", "Legumes"})
        self.assertNotIn(chosen.base.name, {"Soup", "Legumes"})
        self.assertNotIn(chosen.protein.name, {"Soup", "Legumes"})

    def test_same_date_is_idempotent(self):
        state = RotationState()
        first = state.assign(datetime.date(2026, 11, 2), set())
        again = state.assign(datetime.date(2026, 11, 2),
                              {first.base.name, first.protein.name})
        self.assertEqual(again, first)

    def test_weighting_favours_higher_weight_groups(self):
        state = RotationState()
        for offset in range(200):
            state.assign(datetime.date(2026, 1, 1) + datetime.timedelta(days=offset), set())
        oily = state.count_of(group("Oily Fish"))
        meat = state.count_of(group("Meat"))
        self.assertEqual(group("Oily Fish").weight, 2)
        self.assertEqual(group("Meat").weight, 1)
        self.assertAlmostEqual(oily / meat, 2.0, delta=0.25)

    def test_every_group_gets_used(self):
        state = RotationState()
        for offset in range(60):
            state.assign(datetime.date(2026, 1, 1) + datetime.timedelta(days=offset), set())
        for entry in BASE_GROUPS + PROTEIN_GROUPS:
            self.assertGreater(state.count_of(entry), 0, f"{entry.name} never used")

    def test_derive_state_replays_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root, "202609", [day("2026-09-01", enriched=pairing("Soup", "Legumes")).to_dict()])
            write_archive(root, "202610", [day("2026-10-01", enriched=pairing("Soup", "Meat")).to_dict()])
            state = derive_state(root)
            self.assertEqual(state.count_of(group("Soup")), 2)
            self.assertEqual(state.usage["Soup"].last_used, datetime.date(2026, 10, 1))
            self.assertEqual(state.count_of(group("Legumes")), 1)
            # an archived day keeps its original pairing when re-assigned
            self.assertEqual(state.assign(datetime.date(2026, 9, 1), set()),
                              pairing("Soup", "Legumes"))

    def test_derive_state_skips_retired_vocabulary(self):
        """A group removed from food_groups.py must not crash or count."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retired = day("2026-10-01", enriched=pairing("Soup", "Meat")).to_dict()
            retired["dinner_food_groups"]["base"] = "Bread"  # retired in a later version
            write_archive(root, "202610", [
                retired,
                day("2026-10-02", enriched=pairing("Soup", "Legumes")).to_dict(),
            ])
            state = derive_state(root)
            self.assertNotIn(datetime.date(2026, 10, 1), state.assigned)
            self.assertEqual(state.count_of(group("Soup")), 1)
            # the retired day re-assigns cleanly instead of raising
            chosen = state.assign(datetime.date(2026, 10, 1), set())
            self.assertIn(chosen.base, BASE_GROUPS)

    def test_derive_state_ignores_days_without_a_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root, "202610", [day("2026-10-01").to_dict()])
            self.assertEqual(derive_state(root).assigned, {})

    def test_derive_state_on_missing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(derive_state(Path(tmp) / "nope").assigned, {})


class TestPublishUpsert(unittest.TestCase):
    def test_upsert_adds_then_updates_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / LUNCH_CA.filename
            self.assertEqual(upsert_one(menu(day("2026-10-01", "A")), LUNCH_CA, path, DTSTAMP), 1)
            # same date again: replaced, not duplicated
            self.assertEqual(upsert_one(menu(day("2026-10-01", "B")), LUNCH_CA, path, DTSTAMP), 1)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN:VEVENT"), 1)
            self.assertIn("SUMMARY:Menú: x", text)

    def test_upsert_preserves_earlier_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / LUNCH_CA.filename
            upsert_one(menu(day("2026-09-30")), LUNCH_CA, path, DTSTAMP)
            self.assertEqual(upsert_one(menu(day("2026-10-01")), LUNCH_CA, path, DTSTAMP), 2)
            text = path.read_text(encoding="utf-8")
            self.assertIn("UID:20260930-lunch@gaia-menu", text)
            self.assertIn("UID:20261001-lunch@gaia-menu", text)

    def test_events_are_sorted_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / LUNCH_CA.filename
            upsert_one(menu(day("2026-10-30")), LUNCH_CA, path, DTSTAMP)
            upsert_one(menu(day("2026-10-01")), LUNCH_CA, path, DTSTAMP)
            text = path.read_text(encoding="utf-8")
            self.assertLess(text.index("UID:20261001"), text.index("UID:20261030"))

    def test_output_is_a_single_wellformed_vcalendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / LUNCH_CA.filename
            upsert_one(menu(day("2026-10-01")), LUNCH_CA, path, DTSTAMP)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("BEGIN:VCALENDAR"), 1)
            self.assertEqual(text.count("END:VCALENDAR"), 1)
            self.assertTrue(text.startswith("BEGIN:VCALENDAR"))
            self.assertTrue(text.rstrip().endswith("END:VCALENDAR"))

    def test_every_line_ends_crlf_including_preserved_events(self):
        """RFC 5545 wants CRLF. Events re-read from an existing file must
        not come back with the bare LF that read_text() leaves."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / LUNCH_CA.filename
            upsert_one(menu(day("2026-09-30")), LUNCH_CA, path, DTSTAMP)
            upsert_one(menu(day("2026-10-01")), LUNCH_CA, path, DTSTAMP)
            raw = path.read_bytes()
            self.assertEqual(raw.count(b"\n") - raw.count(b"\r\n"), 0, "bare LF found")

    def test_unenriched_days_are_skipped_for_dinner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DINNER_CA.filename
            self.assertEqual(upsert_one(menu(day("2026-10-01")), DINNER_CA, path, DTSTAMP), 0)

    def test_enriched_days_render_a_dinner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / DINNER_CA.filename
            enriched = day("2026-10-01", "Arròs + Salmó", pairing("Soup", "Legumes"))
            self.assertEqual(upsert_one(menu(enriched), DINNER_CA, path, DTSTAMP), 1)
            text = path.read_text(encoding="utf-8")
            self.assertIn("SUMMARY:🍽️ Sopa + Llegums", text)
            self.assertIn("Dinar d'avui: 🧑‍🍳 Arròs + Salmó", text)

    def test_roundtrip_through_parse_existing_events(self):
        block = ("BEGIN:VEVENT\r\nUID:20261001-lunch@gaia-menu\r\n"
                 "DTSTART:20261001T111500Z\r\nSUMMARY:x\r\nEND:VEVENT")
        text = wrap_vcalendar({"20261001-lunch@gaia-menu": block})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.ics"
            path.write_text(text, encoding="utf-8", newline="")
            self.assertEqual(list(parse_existing_events(path)), ["20261001-lunch@gaia-menu"])


class TestMenuRoundTrip(unittest.TestCase):
    def test_enriched_day_survives_a_json_round_trip(self):
        original = menu(day("2026-10-01", "Arròs + Salmó", pairing("Soup", "Legumes")))
        restored = Menu.from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertEqual(restored.to_dict(), original.to_dict())
        self.assertIsNotNone(restored.days[0].enrichment)

    def test_plain_day_carries_no_enrichment_keys(self):
        data = menu(day("2026-10-01")).to_dict()
        self.assertNotIn("title", data["days"][0])
        self.assertNotIn("en", data["days"][0])
        self.assertIsNone(Menu.from_dict(data).days[0].enrichment)


if __name__ == "__main__":
    unittest.main()
