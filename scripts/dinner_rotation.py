#!/usr/bin/env python3
"""Deterministic weighted dinner-pairing rotation.

Each school day gets one base group plus one protein group. Among the
groups a day's lunch leaves eligible, the rotation picks whichever sits
furthest below its weekly target: lowest count/weight, then longest
unused, then declared order. A weight-2 group such as Oily Fish comes up
about twice as often as a weight-1 group such as Meat.

The rotation keeps no state file. derive_state rebuilds the counts by
replaying the pairing recorded on every archived day, oldest first.
Re-assigning a date the archive already covers returns its stored
pairing. Days the archive records under a retired group resolve to no
enrichment at all, so the replay passes over them.
"""
import datetime
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent))
import food_groups  # noqa: E402
from food_groups import BASE_GROUPS, PROTEIN_GROUPS, FoodGroup  # noqa: E402
from models import DinnerPairing, Menu  # noqa: E402

DEFAULT_ARCHIVE = Path(__file__).parent.parent / "archive"


@dataclass(slots=True)
class GroupUsage:
    count: int = 0
    last_used: datetime.date | None = None

    def record(self, day: datetime.date) -> None:
        self.count += 1
        self.last_used = day


@dataclass(slots=True)
class RotationState:
    usage: dict[str, GroupUsage] = field(
        default_factory=lambda: {g.name: GroupUsage() for g in food_groups.FOOD_GROUPS}
    )
    assigned: dict[datetime.date, DinnerPairing] = field(default_factory=dict)

    def count_of(self, group: FoodGroup) -> int:
        return self.usage[group.name].count

    def pick(self, groups: tuple[FoodGroup, ...], excluded: set[str]) -> FoodGroup:
        """The eligible group furthest below its weekly target. Falls back
        to the full set when a lunch excludes every one of them."""
        candidates = [g for g in groups if g.name not in excluded] or list(groups)

        def rank(group: FoodGroup) -> tuple[float, datetime.date, int]:
            used = self.usage[group.name]
            return (used.count / group.weight,
                    used.last_used or datetime.date.min,
                    groups.index(group))

        return min(candidates, key=rank)

    def record(self, day: datetime.date, pairing: DinnerPairing) -> None:
        self.usage[pairing.base.name].record(day)
        self.usage[pairing.protein.name].record(day)
        self.assigned[day] = pairing

    def assign(self, day: datetime.date, excluded: set[str]) -> DinnerPairing:
        """The pairing for `day`, reusing the stored one when the archive
        already covers it."""
        if day in self.assigned:
            return self.assigned[day]
        pairing = DinnerPairing(base=self.pick(BASE_GROUPS, excluded),
                                 protein=self.pick(PROTEIN_GROUPS, excluded))
        self.record(day, pairing)
        return pairing


def iter_archived_months(archive_dir: Path) -> Iterator[Menu]:
    for month_dir in sorted(p for p in archive_dir.glob("*") if p.is_dir()):
        enriched = month_dir / "enriched.json"
        if enriched.exists():
            yield Menu.from_dict(json.loads(enriched.read_text(encoding="utf-8")))


def derive_state(archive_dir: Path = DEFAULT_ARCHIVE) -> RotationState:
    """Rebuilds the rotation by replaying every archived month."""
    state = RotationState()
    if not archive_dir.exists():
        return state
    dated = [(day.date, day.enrichment.pairing)
             for menu in iter_archived_months(archive_dir)
             for day in menu.days if day.enrichment is not None]
    for day, pairing in sorted(dated, key=lambda pair: pair[0]):
        state.record(day, pairing)
    return state
