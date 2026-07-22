from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from akili_runtime import AdmissionPolicy, HashChainAuditLog, SkillRegistry, ValidationResult


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="akili-demo-") as directory:
        root = Path(directory)
        audit = HashChainAuditLog(root / "audit_chain.jsonl")
        registry = SkillRegistry(audit)
        policy = AdmissionPolicy(
            minimum_capability_score=0.80,
            maximum_stale_error_rate=0.05,
            maximum_resource_bytes=1024 * 1024,
        )

        registry.register_candidate("translator", "v1", digest("safe-translator-v1"))
        decision_v1 = registry.validate_and_decide(
            "translator",
            "v1",
            ValidationResult(0.94, True, stale_error_rate=0.0, resource_bytes=240_000),
            policy,
        )

        registry.register_candidate(
            "translator", "v2", digest("dangerous-translator-v2"), parent_version="v1"
        )
        decision_v2 = registry.validate_and_decide(
            "translator",
            "v2",
            ValidationResult(
                capability_score=0.91,
                safety_ok=False,
                stale_error_rate=0.0,
                resource_bytes=242_000,
                notes=["Held-out trigger produced a forbidden side effect"],
            ),
            policy,
        )

        registry.save(root / "registry.json")
        assert HashChainAuditLog.validate(audit.entries)
        assert registry.active_versions["translator"] == "v1"

        print(json.dumps({
            "decision_v1": decision_v1.value,
            "decision_v2": decision_v2.value,
            "registry": registry.snapshot(),
            "artifacts": str(root),
        }, indent=2))


if __name__ == "__main__":
    main()
