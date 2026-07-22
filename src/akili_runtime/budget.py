from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class BudgetCandidate:
    key: str
    bytes: int
    utility: float
    safety_critical: bool = False
    pinned: bool = False


class SkillBudgetController:
    """Deterministic active-bank selection for demonstrations.

    This is a reference policy, not a claimed optimal managed-forgetting algorithm.
    Pinned and safety-critical skills are selected first, then remaining skills by
    utility per byte.
    """

    def select(self, candidates: Sequence[BudgetCandidate], maximum_bytes: int) -> Tuple[List[str], List[str]]:
        if maximum_bytes < 0:
            raise ValueError("maximum_bytes must be non-negative")
        mandatory = sorted(
            (item for item in candidates if item.pinned or item.safety_critical),
            key=lambda item: item.key,
        )
        optional = sorted(
            (item for item in candidates if not (item.pinned or item.safety_critical)),
            key=lambda item: (-(item.utility / max(item.bytes, 1)), -item.utility, item.key),
        )
        selected: List[str] = []
        used = 0
        for item in [*mandatory, *optional]:
            if used + item.bytes <= maximum_bytes:
                selected.append(item.key)
                used += item.bytes
            elif item in mandatory:
                raise ValueError("Mandatory skills exceed the active-bank budget")
        dormant = sorted(item.key for item in candidates if item.key not in selected)
        return selected, dormant
