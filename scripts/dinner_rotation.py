#!/usr/bin/env python3
"""Deterministic weighted dinner-pairing rotation.

Each school day gets one BASE_GROUPS pick + one PROTEIN_GROUPS pick,
preferring whichever eligible category is furthest below its
weight-adjusted share of use (count / WEIGHTS[group], ascending; ties
broken by oldest last-used date, then declared order) - a weight-2
group (e.g. "Oily Fish") is picked roughly twice as often as a weight-1
group (e.g. "Meat"). See README.md "Why these dinner-pairing
frequencies" for where the weights come from.

There is no rotation state file. derive_state() rebuilds the counts by
replaying the "dinner_food_groups" of every archive/<YYYYMM>/enriched.json
in date order. Re-assigning a date already in the archive returns its
stored pairing unchanged; entries naming a category no longer in the
vocabulary are skipped.
"""
import json
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).parent))
from food_groups import BASE_GROUPS, PROTEIN_GROUPS, WEIGHTS  # noqa: E402

DEFAULT_ARCHIVE = Path(__file__).parent.parent / "archive"


def empty_state() -> dict[str, Any]:
    return {
        "usage": {
            "base": {g: {"count": 0, "last_date": None} for g in BASE_GROUPS},
            "protein": {g: {"count": 0, "last_date": None} for g in PROTEIN_GROUPS},
        },
        "by_date": {},
    }


def _record(state: dict[str, Any], date: str, base: str, protein: str) -> None:
    for role, group in (("base", base), ("protein", protein)):
        u = state["usage"][role][group]
        state["usage"][role][group] = {"count": u["count"] + 1, "last_date": date}
    state["by_date"][date] = {"base": base, "protein": protein}


def iter_archived_days(archive_dir: Path) -> Iterator[tuple[str, str, str]]:
    """Yields (date, base, protein) from every archived enriched.json.
    Days with no structured dinner_food_groups, or naming a category no
    longer in the vocabulary, are skipped."""
    for month_dir in sorted(p for p in archive_dir.glob("*") if p.is_dir()):
        enriched = month_dir / "enriched.json"
        if not enriched.exists():
            continue
        data = json.loads(enriched.read_text(encoding="utf-8"))
        for day in data.get("days", []):
            groups = day.get("dinner_food_groups") or {}
            base, protein = groups.get("base"), groups.get("protein")
            if base in BASE_GROUPS and protein in PROTEIN_GROUPS:
                yield day["date"], base, protein


def derive_state(archive_dir: Path = DEFAULT_ARCHIVE) -> dict[str, Any]:
    """Rebuilds rotation usage by replaying the archive, oldest day first."""
    state = empty_state()
    if archive_dir.exists():
        for date, base, protein in sorted(iter_archived_days(archive_dir)):
            _record(state, date, base, protein)
    return state


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
    _record(state, date, base, protein)
    return base, protein
