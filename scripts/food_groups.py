#!/usr/bin/env python3
"""Fixed English/Catalan food-group vocabulary for lunch tagging and
dinner-pairing output.

BASE_GROUPS, PROTEIN_GROUPS - suggestable for dinner (one of each per
day, see dinner_rotation.py); also valid lunch_groups tags.
LUNCH_ONLY_GROUPS - valid lunch_groups tags, never suggested for dinner.
LUNCH_ONLY_IMPLIES maps each to the suggestable group it also excludes.

WEIGHTS give each suggestable group's relative weekly dinner target;
dinner_rotation.py picks whichever eligible group is furthest below its
weight-adjusted share of use. See README.md "Why these dinner-pairing
frequencies" for sourcing.
"""

BASE_GROUPS_EN_TO_CA: dict[str, str] = {
    "Soup": "Sopa",
    "Salad": "Amanida",
    "Vegetables": "Verdures",
    "Pasta": "Pasta",
    "Rice": "Arròs",
    "Potato": "Patata",
    "Grains": "Cereals",
}
BASE_WEIGHTS: dict[str, int] = {
    "Soup": 1, "Salad": 2, "Vegetables": 2, "Pasta": 1,
    "Rice": 1, "Potato": 1, "Grains": 1,
}

PROTEIN_GROUPS_EN_TO_CA: dict[str, str] = {
    "Legumes": "Llegums",
    "Meat": "Carn",
    "Poultry": "Aviram",
    "Fish": "Peix",
    "Oily Fish": "Peix blau",
    "Seafood": "Marisc",
    "Eggs": "Ou",
    "Dairy": "Lactis",
}
PROTEIN_WEIGHTS: dict[str, int] = {
    "Legumes": 2, "Meat": 1, "Poultry": 2, "Fish": 1,
    "Oily Fish": 2, "Seafood": 1, "Eggs": 2, "Dairy": 1,
}

LUNCH_ONLY_EN_TO_CA: dict[str, str] = {
    "Processed Meat": "Carn processada",
}
# A lunch-only tag also excludes this suggestable group from that day's
# dinner pick (same nutritional family - e.g. sausage at lunch means
# dinner shouldn't suggest more "Meat" either).
LUNCH_ONLY_IMPLIES: dict[str, str] = {
    "Processed Meat": "Meat",
}

FOOD_GROUPS_EN_TO_CA: dict[str, str] = {**BASE_GROUPS_EN_TO_CA, **PROTEIN_GROUPS_EN_TO_CA}
BASE_GROUPS: list[str] = list(BASE_GROUPS_EN_TO_CA)
PROTEIN_GROUPS: list[str] = list(PROTEIN_GROUPS_EN_TO_CA)
FOOD_GROUPS: list[str] = list(FOOD_GROUPS_EN_TO_CA)
WEIGHTS: dict[str, int] = {**BASE_WEIGHTS, **PROTEIN_WEIGHTS}

LUNCH_ONLY_GROUPS: list[str] = list(LUNCH_ONLY_EN_TO_CA)
LUNCH_TAGS_EN_TO_CA: dict[str, str] = {**FOOD_GROUPS_EN_TO_CA, **LUNCH_ONLY_EN_TO_CA}
LUNCH_TAGS: list[str] = list(LUNCH_TAGS_EN_TO_CA)
