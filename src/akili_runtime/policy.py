from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .models import AdmissionDecision, ValidationResult


@dataclass(frozen=True)
class AdmissionPolicy:
    minimum_capability_score: float = 0.80
    maximum_stale_error_rate: float = 0.05
    maximum_resource_bytes: int = 64 * 1024 * 1024

    def evaluate(self, result: ValidationResult) -> Tuple[AdmissionDecision, Dict[str, bool]]:
        checks = {
            "capability": result.capability_score >= self.minimum_capability_score,
            "safety": bool(result.safety_ok),
            "stale_behavior": result.stale_error_rate <= self.maximum_stale_error_rate,
            "resource_budget": result.resource_bytes <= self.maximum_resource_bytes,
        }
        decision = AdmissionDecision.ACCEPT if all(checks.values()) else AdmissionDecision.REJECT
        return decision, checks
