#!/usr/bin/env python3
"""Fixed English/Catalan food-group vocabulary for dinner-pairing output.
Dinner recommendations use exactly two of these English words."""

FOOD_GROUPS_EN_TO_CA: dict[str, str] = {
    "Soup": "Sopa",
    "Salad": "Amanida",
    "Vegetables": "Verdures",
    "Pasta": "Pasta",
    "Rice": "Arròs",
    "Potato": "Patata",
    "Legumes": "Llegums",
    "Meat": "Carn",
    "Poultry": "Aviram",
    "Fish": "Peix",
    "Seafood": "Marisc",
    "Eggs": "Ou",
    "Dairy": "Lactis",
    "Bread": "Pa",
    "Fruit": "Fruita",
    "Cereal": "Cereals",
}

FOOD_GROUPS: list[str] = list(FOOD_GROUPS_EN_TO_CA)
