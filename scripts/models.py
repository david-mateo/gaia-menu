#!/usr/bin/env python3
"""The entities that cross stage boundaries, and their JSON shapes.

A Menu holds one month of MenuDay. A MenuDay starts bare from the PDF
and gains an Enrichment once the model has tagged and translated it. An
Enrichment holds a DinnerPairing, which is one base group plus one
protein group.

Resolving a day's food groups is all-or-nothing. When the vocabulary has
retired a group the archive still names, from_dict drops that day's whole
Enrichment, so the day falls back to its untranslated form and the
rotation skips it until the month is enriched again.
"""
import datetime
from dataclasses import dataclass, field
from typing import Any

import food_groups
from food_groups import FoodGroup

LUNCH_EMOJI = "🧑‍🍳 "
DINNER_EMOJI = "🍽️ "


class MenuError(RuntimeError):
    """A menu document did not have the shape this stage expects."""


@dataclass(frozen=True, slots=True)
class DinnerPairing:
    base: FoodGroup
    protein: FoodGroup

    @property
    def english(self) -> str:
        return f"{self.base.name} + {self.protein.name}"

    @property
    def catalan(self) -> str:
        return f"{self.base.catalan} + {self.protein.catalan}"

    def to_dict(self) -> dict[str, str]:
        return {"base": self.base.name, "protein": self.protein.name}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DinnerPairing | None":
        base = food_groups.find(data.get("base", ""))
        protein = food_groups.find(data.get("protein", ""))
        if base is None or protein is None:
            return None
        return cls(base, protein)


@dataclass(frozen=True, slots=True)
class Enrichment:
    """What the model contributed for one day, plus the pairing the
    rotation assigned it."""

    lunch_groups: tuple[FoodGroup, ...]
    pairing: DinnerPairing
    title_ca: str
    title_en: str
    items_en: tuple[str, ...]
    dessert_en: str | None

    @property
    def lunch_title_ca(self) -> str:
        return LUNCH_EMOJI + self.title_ca

    @property
    def lunch_title_en(self) -> str:
        return LUNCH_EMOJI + self.title_en

    @property
    def dinner_ca(self) -> str:
        return DINNER_EMOJI + self.pairing.catalan

    @property
    def dinner_en(self) -> str:
        return DINNER_EMOJI + self.pairing.english

    def to_dict(self) -> dict[str, Any]:
        return {
            "lunch_food_groups": food_groups.names(self.lunch_groups),
            "dinner_food_groups": self.pairing.to_dict(),
            "title": self.lunch_title_ca,
            "dinner": self.dinner_ca,
            "en": {
                "items": list(self.items_en),
                "dessert": self.dessert_en,
                "title": self.lunch_title_en,
                "dinner": self.dinner_en,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Enrichment | None":
        pairing_data = data.get("dinner_food_groups")
        english = data.get("en")
        if not pairing_data or not english:
            return None
        pairing = DinnerPairing.from_dict(pairing_data)
        if pairing is None:
            return None
        groups = [food_groups.find(n) for n in data.get("lunch_food_groups", [])]
        if any(g is None for g in groups):
            return None
        return cls(
            lunch_groups=tuple(g for g in groups if g is not None),
            pairing=pairing,
            title_ca=data["title"].removeprefix(LUNCH_EMOJI),
            title_en=english["title"].removeprefix(LUNCH_EMOJI),
            items_en=tuple(english["items"]),
            dessert_en=english["dessert"],
        )


@dataclass(slots=True)
class MenuDay:
    """One dated school day that has a menu."""

    date: datetime.date
    weekday: str
    items: list[str]
    dessert: str | None
    allergens: list[int] | None
    day_label_from_pdf: int | None
    date_label_mismatch: bool
    enrichment: Enrichment | None = None

    @property
    def compact_date(self) -> str:
        """YYYYMMDD, as .ics UIDs and DTSTART values want it."""
        return self.date.strftime("%Y%m%d")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "date": self.date.isoformat(),
            "weekday": self.weekday,
            "items": list(self.items),
            "dessert": self.dessert,
            "allergens": list(self.allergens) if self.allergens is not None else None,
            "day_label_from_pdf": self.day_label_from_pdf,
            "date_label_mismatch": self.date_label_mismatch,
        }
        if self.enrichment is not None:
            data.update(self.enrichment.to_dict())
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MenuDay":
        return cls(
            date=datetime.date.fromisoformat(data["date"]),
            weekday=data["weekday"],
            items=list(data["items"]),
            dessert=data["dessert"],
            allergens=data["allergens"],
            day_label_from_pdf=data["day_label_from_pdf"],
            date_label_mismatch=data["date_label_mismatch"],
            enrichment=Enrichment.from_dict(data),
        )


@dataclass(slots=True)
class Menu:
    """One month. Closure days and days with no menu are already dropped."""

    year: int
    month: int
    days: list[MenuDay] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"year": self.year, "month": self.month,
                "days": [d.to_dict() for d in self.days]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Menu":
        try:
            return cls(year=data["year"], month=data["month"],
                        days=[MenuDay.from_dict(d) for d in data["days"]])
        except (KeyError, TypeError, ValueError) as e:
            raise MenuError(f"not a menu document: {e}") from e


@dataclass(frozen=True, slots=True)
class DayResponse:
    """One entry of the response.json the model writes."""

    date: datetime.date
    items_en: tuple[str, ...]
    dessert_en: str | None
    title_ca: str
    title_en: str
    lunch_groups: tuple[FoodGroup, ...]

    REQUIRED = ("ca_title", "en_title", "en_items", "lunch_groups")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DayResponse":
        where = data.get("date", "<no date>")
        for key in cls.REQUIRED:
            if key not in data:
                raise MenuError(f"{where}: response missing '{key}'")
        if not data["lunch_groups"]:
            raise MenuError(f"{where}: 'lunch_groups' is empty")

        groups = []
        for name in data["lunch_groups"]:
            group = food_groups.find(name)
            if group is None:
                raise MenuError(
                    f"{where}: lunch group '{name}' is not one of "
                    f"{food_groups.names(food_groups.FOOD_GROUPS)}"
                )
            groups.append(group)

        return cls(
            date=datetime.date.fromisoformat(data["date"]),
            items_en=tuple(data["en_items"]),
            dessert_en=data.get("en_dessert"),
            title_ca=data["ca_title"],
            title_en=data["en_title"],
            lunch_groups=tuple(groups),
        )


@dataclass(frozen=True, slots=True)
class EnrichmentResponse:
    new_translations: dict[str, str]
    days: dict[datetime.date, DayResponse]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnrichmentResponse":
        days = [DayResponse.from_dict(d) for d in data.get("days", [])]
        return cls(
            new_translations=data.get("new_translations", {}),
            days={d.date: d for d in days},
        )
