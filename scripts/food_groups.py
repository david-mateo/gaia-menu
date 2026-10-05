#!/usr/bin/env python3
"""The closed food-group vocabulary used to tag lunches and to build
dinner pairings.

Each group carries its Catalan name, its role, and its relative weekly
dinner target in one place. dinner_rotation.py picks whichever eligible
group is furthest below that target. README.md "Why these dinner-pairing
frequencies" has the sourcing for the weights.
"""
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Where a group may appear."""

    BASE = "base"  # the starch or vegetable half of a dinner pairing
    PROTEIN = "protein"  # the protein half
    LUNCH_ONLY = "lunch_only"  # taggable on a lunch, never suggested for dinner


@dataclass(frozen=True, slots=True)
class FoodGroup:
    """One vocabulary entry. `name` is the key used in JSON and in the
    published .ics summaries."""

    name: str
    catalan: str
    role: Role
    weight: int = 1
    excludes: str | None = None  # LUNCH_ONLY only: group it also rules out

    @property
    def suggestable(self) -> bool:
        return self.role is not Role.LUNCH_ONLY


FOOD_GROUPS: tuple[FoodGroup, ...] = (
    FoodGroup("Soup", "Sopa", Role.BASE),
    FoodGroup("Salad", "Amanida", Role.BASE, weight=2),
    FoodGroup("Vegetables", "Verdures", Role.BASE, weight=2),
    FoodGroup("Pasta", "Pasta", Role.BASE),
    FoodGroup("Rice", "Arròs", Role.BASE),
    FoodGroup("Potato", "Patata", Role.BASE),
    FoodGroup("Grains", "Cereals", Role.BASE),
    FoodGroup("Legumes", "Llegums", Role.PROTEIN, weight=2),
    FoodGroup("Meat", "Carn", Role.PROTEIN),
    FoodGroup("Poultry", "Aviram", Role.PROTEIN, weight=2),
    FoodGroup("Fish", "Peix", Role.PROTEIN),
    FoodGroup("Oily Fish", "Peix blau", Role.PROTEIN, weight=2),
    FoodGroup("Seafood", "Marisc", Role.PROTEIN),
    FoodGroup("Eggs", "Ou", Role.PROTEIN, weight=2),
    FoodGroup("Dairy", "Lactis", Role.PROTEIN),
    FoodGroup("Processed Meat", "Carn processada", Role.LUNCH_ONLY, excludes="Meat"),
)


def of_role(role: Role) -> tuple[FoodGroup, ...]:
    return tuple(g for g in FOOD_GROUPS if g.role is role)


BASE_GROUPS = of_role(Role.BASE)
PROTEIN_GROUPS = of_role(Role.PROTEIN)
LUNCH_ONLY_GROUPS = of_role(Role.LUNCH_ONLY)

_BY_NAME = {g.name: g for g in FOOD_GROUPS}


def find(name: str) -> FoodGroup | None:
    """The group called `name`, or None if the vocabulary has retired it."""
    return _BY_NAME.get(name)


def names(groups: tuple[FoodGroup, ...]) -> list[str]:
    return [g.name for g in groups]


def excluded_by(group: FoodGroup) -> set[str]:
    """Group names a lunch tag rules out of that day's dinner pairing: the
    tag itself, plus whatever it stands in for (sausage at lunch also
    rules out plain Meat)."""
    if group.excludes:
        return {group.name, group.excludes}
    return {group.name}
