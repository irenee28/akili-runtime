from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .audit import HashChainAuditLog
from .models import AdmissionDecision, SkillState, SkillVersion, ValidationResult
from .policy import AdmissionPolicy


class SkillRegistry:
    def __init__(self, audit: Optional[HashChainAuditLog] = None) -> None:
        self.audit = audit or HashChainAuditLog()
        self.versions: Dict[str, SkillVersion] = {}
        self.active_versions: Dict[str, str] = {}

    def register_candidate(
        self,
        skill: str,
        version: str,
        artifact_hash: str,
        parent_version: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> SkillVersion:
        item = SkillVersion(
            skill=skill,
            version=version,
            artifact_hash=artifact_hash,
            parent_version=parent_version,
            metadata=dict(metadata or {}),
        )
        if item.key in self.versions:
            existing = self.versions[item.key]
            if existing.artifact_hash != artifact_hash:
                raise ValueError(f"Write-once violation for {item.key}")
            return existing
        self.versions[item.key] = item
        self.audit.append("CANDIDATE_REGISTERED", {"key": item.key, "artifact_hash": artifact_hash})
        return item

    def validate_and_decide(
        self,
        skill: str,
        version: str,
        result: ValidationResult,
        policy: AdmissionPolicy,
    ) -> AdmissionDecision:
        key = f"{skill}@{version}"
        if key not in self.versions:
            raise KeyError(key)
        item = self.versions[key]
        if item.validation is not None:
            if item.validation != result:
                raise ValueError(f"Validation is immutable for {key}")
            decision, _ = policy.evaluate(result)
            return decision
        decision, checks = policy.evaluate(result)
        item.validation = result
        self.audit.append(
            "CANDIDATE_VALIDATED",
            {"key": key, "decision": decision.value, "checks": checks, "result": result.to_dict()},
        )
        if decision is AdmissionDecision.ACCEPT:
            previous = self.active_versions.get(skill)
            if previous is not None and previous != version:
                previous_item = self.versions[f"{skill}@{previous}"]
                previous_item.state = SkillState.DORMANT
                self.audit.append("VERSION_DORMANT", {"key": previous_item.key, "superseded_by": key})
            item.state = SkillState.ACTIVE
            self.active_versions[skill] = version
            self.audit.append("VERSION_ACTIVATED", {"key": key})
        else:
            item.state = SkillState.ROLLED_BACK
            self.audit.append("VERSION_ROLLED_BACK", {"key": key})
        return decision

    def restore(self, skill: str, version: str) -> None:
        key = f"{skill}@{version}"
        item = self.versions[key]
        if item.state in {SkillState.ROLLED_BACK, SkillState.DELETED}:
            raise ValueError(f"Cannot restore {key} from state {item.state.value}")
        current = self.active_versions.get(skill)
        if current and current != version:
            self.versions[f"{skill}@{current}"].state = SkillState.DORMANT
        item.state = SkillState.ACTIVE
        self.active_versions[skill] = version
        self.audit.append("VERSION_RESTORED", {"key": key, "previous": current})

    def mark_deleted(self, skill: str, version: str) -> None:
        key = f"{skill}@{version}"
        item = self.versions[key]
        if self.active_versions.get(skill) == version:
            raise ValueError("An active version cannot be deleted")
        item.state = SkillState.DELETED
        self.audit.append("VERSION_DELETED", {"key": key})

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active_versions": dict(sorted(self.active_versions.items())),
            "versions": {key: value.to_dict() for key, value in sorted(self.versions.items())},
            "audit_head": self.audit.head,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
