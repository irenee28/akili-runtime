from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from akili_runtime import (
    AdmissionDecision,
    AdmissionPolicy,
    BudgetCandidate,
    HashChainAuditLog,
    SkillBudgetController,
    SkillRegistry,
    SkillState,
    ValidationResult,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class RuntimeTests(unittest.TestCase):
    def test_accept_supersede_reject_and_restore(self) -> None:
        audit = HashChainAuditLog()
        registry = SkillRegistry(audit)
        policy = AdmissionPolicy(0.8, 0.05, 1_000)

        registry.register_candidate("skill", "v1", digest("v1"))
        self.assertEqual(
            registry.validate_and_decide("skill", "v1", ValidationResult(0.9, True, 0.0, 100), policy),
            AdmissionDecision.ACCEPT,
        )
        registry.register_candidate("skill", "v2", digest("v2"), parent_version="v1")
        self.assertEqual(
            registry.validate_and_decide("skill", "v2", ValidationResult(0.95, True, 0.0, 100), policy),
            AdmissionDecision.ACCEPT,
        )
        self.assertEqual(registry.versions["skill@v1"].state, SkillState.DORMANT)
        registry.register_candidate("skill", "v3", digest("v3"), parent_version="v2")
        self.assertEqual(
            registry.validate_and_decide("skill", "v3", ValidationResult(0.99, False, 0.0, 100), policy),
            AdmissionDecision.REJECT,
        )
        self.assertEqual(registry.active_versions["skill"], "v2")
        registry.restore("skill", "v1")
        self.assertEqual(registry.active_versions["skill"], "v1")
        self.assertTrue(HashChainAuditLog.validate(audit.entries))

    def test_tamper_is_detected(self) -> None:
        audit = HashChainAuditLog()
        audit.append("A", {"x": 1})
        audit.append("B", {"y": 2})
        tampered = copy.deepcopy(audit.entries)
        tampered[0]["payload"]["x"] = 99
        self.assertFalse(HashChainAuditLog.validate(tampered))

    def test_write_once(self) -> None:
        registry = SkillRegistry()
        registry.register_candidate("s", "v1", digest("a"))
        registry.register_candidate("s", "v1", digest("a"))
        with self.assertRaises(ValueError):
            registry.register_candidate("s", "v1", digest("b"))

    def test_budget_controller(self) -> None:
        controller = SkillBudgetController()
        selected, dormant = controller.select([
            BudgetCandidate("critical", 40, 0.1, safety_critical=True),
            BudgetCandidate("high", 30, 0.9),
            BudgetCandidate("low", 30, 0.1),
        ], 70)
        self.assertEqual(selected, ["critical", "high"])
        self.assertEqual(dormant, ["low"])


if __name__ == "__main__":
    unittest.main()
