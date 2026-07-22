from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SkillState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    CONSOLIDATED = "CONSOLIDATED"
    DORMANT = "DORMANT"
    ROLLED_BACK = "ROLLED_BACK"
    DELETED = "DELETED"


class AdmissionDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ValidationResult:
    capability_score: float
    safety_ok: bool
    stale_error_rate: float = 0.0
    resource_bytes: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillVersion:
    skill: str
    version: str
    artifact_hash: str
    parent_version: Optional[str]
    state: SkillState = SkillState.CANDIDATE
    validation: Optional[ValidationResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.skill}@{self.version}"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        if self.validation is not None:
            payload["validation"] = self.validation.to_dict()
        return payload
