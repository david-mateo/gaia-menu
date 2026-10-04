#!/usr/bin/env python3
"""Deterministic weighted dinner-pairing rotation.

Each school day gets one BASE_GROUPS pick + one PROTEIN_GROUPS pick,
preferring whichever eligible category is furthest below its
weight-adjusted share of use (count / WEIGHTS[group], ascending; ties
broken by oldest last-used date, then declared order) - so a
weight-2 group (e.g. "Oily Fish") is picked roughly twice as often as a
weight-1 group (e.g. "Meat"), not at the same rate. See README.md "Why
these dinner-pairing frequencies" for where the weights come from.

State persists in data/dinner_rotation.json, keyed by date:
re-assigning an already-assigned date returns the stored pairing
unchanged instead of picking again and skewing the counts.
"""
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from food_groups import BASE_GROUPS, PROTEIN_GROUPS, WEIGHTS  # noqa: E402

DEFAULT_ROTATION = Path(__file__).parent.parent / "data" / "dinner_rotation.json"


def load_state(path: Path) -> dict[str, Any]:
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    usage = state.setdefault("usage", {"base": {}, "protein": {}})
    for role, groups in (("base", BASE_GROUPS), ("protein", PROTEIN_GROUPS)):
        for g in groups:
            usage[role].setdefault(g, {"count": 0, "last_date": None})
    state.setdefault("by_date", {})
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _pick(usage: dict[str, Any], groups: list[str], excluded: set[str]) -> str:
    candidates = [g for g in groups if g not in excluded] or list(groups)

    def key(g: str) -> tuple[float, str, int]:
        u = usage[g]
        return (u["count"] / WEIGHTS[g], u["last_date"] or "", groups.index(g))

    return min(candidates, key=key)


def assign(state: dict[str, Any], date: str, excluded: set[str]) -> tuple[str, str]:
    """Returns (base, protein) for `date`. Reuses a prior assignment for
    the same date if one exists; otherwise picks and records one,
    mutating `state`."""
    if date in state["by_date"]:
        d = state["by_date"][date]
        return d["base"], d["protein"]

    base = _pick(state["usage"]["base"], BASE_GROUPS, excluded)
    protein = _pick(state["usage"]["protein"], PROTEIN_GROUPS, excluded)
    state["usage"]["base"][base] = {"count": state["usage"]["base"][base]["count"] + 1, "last_date": date}
    state["usage"]["protein"][protein] = {
        "count": state["usage"]["protein"][protein]["count"] + 1, "last_date": date
    }
    state["by_date"][date] = {"base": base, "protein": protein}
    return base, protein
