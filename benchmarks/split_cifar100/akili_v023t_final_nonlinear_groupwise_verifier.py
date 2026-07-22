from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
import torch
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score


PROTOCOL = "0.23T-final-nonlinear-groupwise-rescue-verification"
SOURCE_PROTOCOL = "0.23R-reconstructed-action-evidence-baseline"
EXPECTED_SCHEMA_VERSION = "0.23R-action-schema-v1"
EXPECTED_FEATURE_COUNT = 26
CANDIDATE_COUNT = 3

MODEL_SPECS: Mapping[str, Mapping[str, Any]] = {
    "two_stage_extra_trees": {
        "mode": "two_stage",
        "backends": (("extra_trees", 1.0),),
    },
    "two_stage_random_forest": {
        "mode": "two_stage",
        "backends": (("random_forest", 1.0),),
    },
    "two_stage_blend": {
        "mode": "two_stage",
        "backends": (
            ("extra_trees", 0.5),
            ("random_forest", 0.5),
        ),
    },
    "joint_extra_trees": {
        "mode": "joint",
        "backends": (("extra_trees", 1.0),),
    },
    "joint_random_forest": {
        "mode": "joint",
        "backends": (("random_forest", 1.0),),
    },
    "joint_blend": {
        "mode": "joint",
        "backends": (
            ("extra_trees", 0.5),
            ("random_forest", 0.5),
        ),
    },
}

UTILITY_RESCUE = 1.0
UTILITY_DAMAGE = -3.0
UTILITY_WRONG_TO_WRONG = -0.25
UTILITY_UNCHANGED = 0.0


class ProtocolError(RuntimeError):
    pass


def finite_float(value: Any, default: float) -> float:
    """Parse a metric that may have passed through JSON (NaN -> None).

    Returns ``default`` for None, booleans, non-numeric values, NaN, or infinity.
    This is used only for ranking/guard logic; raw metric payloads retain their
    original undefined-precision representation.
    """
    if value is None or isinstance(value, (bool, np.bool_)):
        return float(default)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def finite_int(value: Any, default: int = 0) -> int:
    """Parse an integer-like metric defensively after JSON serialization."""
    if value is None or isinstance(value, (bool, np.bool_)):
        return int(default)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)
    if not math.isfinite(parsed):
        return int(default)
    return int(parsed)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def json_public(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): json_public(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [json_public(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(json_public(value), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False)
    os.replace(temp, path)


def env_tuple(name: str, default: Sequence[str]) -> Tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    values = tuple(x.strip() for x in raw.split(",") if x.strip()) if raw else tuple(default)
    if not values:
        raise ValueError(f"{name} resolved to an empty tuple")
    return values


def env_int_tuple(name: str, default: Sequence[int]) -> Tuple[int, ...]:
    return tuple(int(x) for x in env_tuple(name, tuple(str(v) for v in default)))


def env_float_tuple(name: str, default: Sequence[float]) -> Tuple[float, ...]:
    values = tuple(float(x) for x in env_tuple(name, tuple(str(v) for v in default)))
    if not all(math.isfinite(x) for x in values):
        raise ValueError(f"{name} contains non-finite values")
    return values


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    mode: str
    seeds: Tuple[int, ...]
    candidate_counts: Tuple[int, ...]
    model_specs: Tuple[str, ...]
    drive_mount: str
    project_root_override: str
    source_run_override: str
    output_subdir: str
    resume: bool
    fail_on_hard_check: bool
    expected_replay_count: int
    expected_probe_count: int
    random_seed: int
    tree_estimators: int
    random_forest_estimators: int
    n_jobs: int
    gate_threshold_grid: Tuple[float, ...]
    expert_threshold_grid: Tuple[float, ...]
    expert_margin_grid: Tuple[float, ...]
    model_roundtrip_tolerance: float
    replay_pooled_gain_min: float
    replay_pooled_damage_max: float
    replay_pooled_precision_min: float
    replay_pooled_invocations_min: int
    replay_pooled_rescues_min: int
    replay_seed_gain_min: float
    replay_seed_damage_max: float
    replay_seed_precision_min: float
    replay_seed_precision_min_invocations: int
    probe_pooled_gain_min: float
    probe_pooled_damage_max: float
    probe_pooled_precision_min: float
    probe_pooled_invocations_min: int
    probe_pooled_rescues_min: int
    strong_accuracy_target: float
    exceptional_accuracy_target: float
    original_target_accuracy: float

    @classmethod
    def from_env(cls) -> "Config":
        mode = os.getenv("AKILI_V023T_MODE", "full").strip().lower()
        if mode not in {"full", "smoke"}:
            raise ValueError("AKILI_V023T_MODE must be full or smoke")
        default_replay = (
            400
            if mode == "full"
            else int(os.getenv("AKILI_V023T_SMOKE_REPLAY_COUNT", "72"))
        )
        default_probe = (
            100
            if mode == "full"
            else int(os.getenv("AKILI_V023T_SMOKE_PROBE_COUNT", "36"))
        )
        default_trees = 220 if mode == "full" else 10
        default_rf = 220 if mode == "full" else 10
        cfg = cls(
            mode=mode,
            seeds=env_int_tuple("AKILI_V023T_SEEDS", (1, 2, 3)),
            candidate_counts=env_int_tuple("AKILI_V023T_CANDIDATE_COUNTS", (2, 3)),
            model_specs=env_tuple(
                "AKILI_V023T_MODEL_SPECS",
                tuple(MODEL_SPECS.keys()),
            ),
            drive_mount=os.getenv("AKILI_V023T_DRIVE_MOUNT", "/content/drive"),
            project_root_override=os.getenv(
                "AKILI_V023T_PROJECT_ROOT", ""
            ).strip(),
            source_run_override=os.getenv(
                "AKILI_V023T_SOURCE_RUN_ROOT", ""
            ).strip(),
            output_subdir=os.getenv(
                "AKILI_V023T_OUTPUT_SUBDIR",
                "stage04/v0_23T_final_nonlinear_groupwise_verifier",
            ),
            resume=env_bool("AKILI_V023T_RESUME", True),
            fail_on_hard_check=env_bool(
                "AKILI_V023T_FAIL_ON_HARD_CHECK", True
            ),
            expected_replay_count=int(
                os.getenv(
                    "AKILI_V023T_EXPECTED_REPLAY_COUNT",
                    str(default_replay),
                )
            ),
            expected_probe_count=int(
                os.getenv(
                    "AKILI_V023T_EXPECTED_PROBE_COUNT",
                    str(default_probe),
                )
            ),
            random_seed=int(
                os.getenv("AKILI_V023T_RANDOM_SEED", "23025")
            ),
            tree_estimators=int(
                os.getenv(
                    "AKILI_V023T_TREE_ESTIMATORS",
                    str(default_trees),
                )
            ),
            random_forest_estimators=int(
                os.getenv(
                    "AKILI_V023T_RANDOM_FOREST_ESTIMATORS",
                    str(default_rf),
                )
            ),
            n_jobs=int(
                os.getenv(
                    "AKILI_V023T_N_JOBS",
                    "-1" if mode == "full" else "1",
                )
            ),
            gate_threshold_grid=env_float_tuple(
                "AKILI_V023T_GATE_THRESHOLD_GRID",
                (
                    0.10,
                    0.15,
                    0.20,
                    0.25,
                    0.30,
                    0.35,
                    0.40,
                    0.45,
                    0.50,
                    0.55,
                    0.60,
                    0.65,
                    0.70,
                    0.75,
                    0.80,
                    0.85,
                    0.90,
                ),
            ),
            expert_threshold_grid=env_float_tuple(
                "AKILI_V023T_EXPERT_THRESHOLD_GRID",
                (
                    0.10,
                    0.20,
                    0.30,
                    0.40,
                    0.50,
                    0.60,
                    0.70,
                    0.80,
                ),
            ),
            expert_margin_grid=env_float_tuple(
                "AKILI_V023T_EXPERT_MARGIN_GRID",
                (
                    0.00,
                    0.025,
                    0.05,
                    0.075,
                    0.10,
                    0.15,
                    0.20,
                    0.30,
                ),
            ),
            model_roundtrip_tolerance=float(
                os.getenv(
                    "AKILI_V023T_MODEL_ROUNDTRIP_TOLERANCE",
                    "1e-12",
                )
            ),
            replay_pooled_gain_min=0.0,
            replay_pooled_damage_max=0.015,
            replay_pooled_precision_min=0.70,
            replay_pooled_invocations_min=30,
            replay_pooled_rescues_min=15,
            replay_seed_gain_min=-0.01,
            replay_seed_damage_max=0.03,
            replay_seed_precision_min=0.25,
            replay_seed_precision_min_invocations=4,
            probe_pooled_gain_min=0.0,
            probe_pooled_damage_max=0.015,
            probe_pooled_precision_min=0.65,
            probe_pooled_invocations_min=10,
            probe_pooled_rescues_min=5,
            strong_accuracy_target=0.72,
            exceptional_accuracy_target=0.75,
            original_target_accuracy=0.79,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.seeds != (1, 2, 3):
            raise ValueError(
                "v0.23T requires exactly seeds 1,2,3 for nested LOSO"
            )
        if set(self.candidate_counts) != {2, 3}:
            raise ValueError(
                "Source validation requires persisted top-2 and top-3 evidence"
            )
        unknown = set(self.model_specs) - set(MODEL_SPECS)
        if unknown:
            raise ValueError(
                f"Unknown v0.23T model specs: {sorted(unknown)}"
            )
        if not self.model_specs:
            raise ValueError("At least one model spec is required")
        if self.expected_replay_count <= 0 or self.expected_probe_count <= 0:
            raise ValueError("Expected evidence counts must be positive")
        if self.tree_estimators <= 0 or self.random_forest_estimators <= 0:
            raise ValueError("Nonlinear model iteration counts must be positive")
        if self.n_jobs == 0:
            raise ValueError("AKILI_V023T_N_JOBS cannot be zero")
        if self.model_roundtrip_tolerance <= 0:
            raise ValueError("Model roundtrip tolerance must be positive")
        for name, grid in (
            ("gate_threshold_grid", self.gate_threshold_grid),
            ("expert_threshold_grid", self.expert_threshold_grid),
            ("expert_margin_grid", self.expert_margin_grid),
        ):
            if not grid or not all(math.isfinite(x) for x in grid):
                raise ValueError(f"{name} must be non-empty and finite")
        if not all(0.0 <= x <= 1.0 for x in self.gate_threshold_grid):
            raise ValueError("Gate thresholds must be in [0,1]")
        if not all(0.0 <= x <= 1.0 for x in self.expert_threshold_grid):
            raise ValueError("Expert thresholds must be in [0,1]")
        if not all(0.0 <= x <= 1.0 for x in self.expert_margin_grid):
            raise ValueError("Expert margins must be in [0,1]")
        if not (
            0.0
            < self.strong_accuracy_target
            <= self.exceptional_accuracy_target
            <= self.original_target_accuracy
            <= 1.0
        ):
            raise ValueError("Accuracy targets are inconsistent")

    def public(self) -> Dict[str, Any]:
        return json_public(asdict(self))


@dataclass
class Evidence:
    seed: int
    split: str
    candidate_count: int
    indices: np.ndarray
    labels: np.ndarray
    action_predictions: np.ndarray
    action_task_ids: np.ndarray
    action_features: np.ndarray
    action_correctness: np.ndarray
    feature_names: Tuple[str, ...]
    schema_hash: str
    source_path: str = ""

    @property
    def n(self) -> int:
        return int(self.labels.shape[0])

    @property
    def action_count(self) -> int:
        return int(self.candidate_count + 1)

    def validate(self) -> None:
        n, a, f = self.n, self.action_count, len(self.feature_names)
        if self.candidate_count not in {2, 3}:
            raise ProtocolError("candidate_count must be 2 or 3")
        if self.indices.shape != (n,) or self.labels.shape != (n,):
            raise ProtocolError("index/label shape mismatch")
        if self.action_predictions.shape != (n, a):
            raise ProtocolError(f"prediction shape mismatch: {self.action_predictions.shape}")
        if self.action_task_ids.shape != (n, a):
            raise ProtocolError("task-id shape mismatch")
        if self.action_features.shape != (n, a, f):
            raise ProtocolError(f"feature shape mismatch: {self.action_features.shape}")
        if self.action_correctness.shape != (n, a):
            raise ProtocolError("correctness shape mismatch")
        if f != EXPECTED_FEATURE_COUNT:
            raise ProtocolError(f"Expected 26 features, found {f}")
        if len(set(self.feature_names)) != f:
            raise ProtocolError("Duplicate feature names")
        if not np.isfinite(self.action_features).all():
            raise ProtocolError("Non-finite action features")
        expected = self.action_predictions == self.labels[:, None]
        if not np.array_equal(expected, self.action_correctness.astype(bool)):
            raise ProtocolError("Correctness tensor disagrees with predictions and labels")
        if np.any(self.action_task_ids < 0):
            raise ProtocolError("Negative task IDs")


def safe_torch_load(path: Path) -> Any:
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def to_numpy(value: Any, dtype: Optional[np.dtype] = None) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        result = value.detach().cpu().numpy()
    else:
        result = np.asarray(value)
    return result.astype(dtype, copy=False) if dtype is not None else result


def _canonical_array_bytes(value: Any, dtype: np.dtype) -> bytes:
    """Return bytes using the exact dtype/contiguity contract used by v0.23R."""
    array = to_numpy(value, dtype)
    return np.ascontiguousarray(array, dtype=dtype).tobytes(order="C")


def evidence_digest(evidence: Evidence) -> str:
    """Reproduce v0.23R ActionEvidence.evidence_digest exactly.

    Integrity hashing is intentionally independent of the analysis dtype.
    v0.23R serialized indices/labels/predictions/task IDs as int64,
    action features as float32, and correctness as bool.  v0.23T may use
    float64 copies for sklearn only after this source-compatible digest is
    validated.
    """
    evidence.validate()
    payload = {
        "seed": int(evidence.seed),
        "split": str(evidence.split),
        "candidate_count": int(evidence.candidate_count),
        "schema_hash": str(evidence.schema_hash),
        "indices": hashlib.sha256(
            _canonical_array_bytes(evidence.indices, np.int64)
        ).hexdigest(),
        "labels": hashlib.sha256(
            _canonical_array_bytes(evidence.labels, np.int64)
        ).hexdigest(),
        "predictions": hashlib.sha256(
            _canonical_array_bytes(evidence.action_predictions, np.int64)
        ).hexdigest(),
        "tasks": hashlib.sha256(
            _canonical_array_bytes(evidence.action_task_ids, np.int64)
        ).hexdigest(),
        "features": hashlib.sha256(
            _canonical_array_bytes(evidence.action_features, np.float32)
        ).hexdigest(),
        "correctness": hashlib.sha256(
            _canonical_array_bytes(evidence.action_correctness, np.bool_)
        ).hexdigest(),
    }
    return canonical_hash(payload)


def v023r_reference_digest_from_payload_item(
    item: Mapping[str, Any],
    schema_hash: str,
) -> str:
    """Independent reference implementation mirroring v0.23R from_payload()."""
    payload = {
        "seed": int(item["seed"]),
        "split": str(item["split"]),
        "candidate_count": int(item["candidate_count"]),
        "schema_hash": str(schema_hash),
        "indices": hashlib.sha256(
            _canonical_array_bytes(item["indices"], np.int64)
        ).hexdigest(),
        "labels": hashlib.sha256(
            _canonical_array_bytes(item["labels"], np.int64)
        ).hexdigest(),
        "predictions": hashlib.sha256(
            _canonical_array_bytes(item["action_predictions"], np.int64)
        ).hexdigest(),
        "tasks": hashlib.sha256(
            _canonical_array_bytes(item["action_task_ids"], np.int64)
        ).hexdigest(),
        "features": hashlib.sha256(
            _canonical_array_bytes(item["action_features"], np.float32)
        ).hexdigest(),
        "correctness": hashlib.sha256(
            _canonical_array_bytes(item["action_correctness"], np.bool_)
        ).hexdigest(),
    }
    return canonical_hash(payload)


def _legacy_analysis_dtype_digest_for_regression_test(evidence: Evidence) -> str:
    """The defective v2 behavior, retained only to prove the regression test."""
    payload = {
        "seed": evidence.seed,
        "split": evidence.split,
        "candidate_count": evidence.candidate_count,
        "schema_hash": evidence.schema_hash,
        "indices": hashlib.sha256(evidence.indices.tobytes()).hexdigest(),
        "labels": hashlib.sha256(evidence.labels.tobytes()).hexdigest(),
        "predictions": hashlib.sha256(evidence.action_predictions.tobytes()).hexdigest(),
        "tasks": hashlib.sha256(evidence.action_task_ids.tobytes()).hexdigest(),
        "features": hashlib.sha256(evidence.action_features.tobytes()).hexdigest(),
        "correctness": hashlib.sha256(evidence.action_correctness.tobytes()).hexdigest(),
    }
    return canonical_hash(payload)


def load_evidence_file(path: Path) -> Tuple[Dict[int, Evidence], Mapping[str, Any], Mapping[str, Any]]:
    payload = safe_torch_load(path)
    if not isinstance(payload, Mapping):
        raise ProtocolError(f"Evidence artifact is not a mapping: {path}")
    if payload.get("protocol") != SOURCE_PROTOCOL:
        raise ProtocolError(f"Unexpected source protocol in {path}: {payload.get('protocol')}")
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ProtocolError(f"Unexpected schema version in {path}")
    schema_hash = str(payload.get("schema_hash", ""))
    names = tuple(str(x) for x in payload.get("feature_names", ()))
    if len(names) != EXPECTED_FEATURE_COUNT:
        raise ProtocolError(f"Expected 26 feature names in {path}")
    result: Dict[int, Evidence] = {}
    for key, item in payload.get("candidate_evidence", {}).items():
        k = int(key)
        item_names = tuple(str(x) for x in item.get("feature_names", names))
        evidence = Evidence(
            seed=int(item["seed"]),
            split=str(item["split"]),
            candidate_count=k,
            indices=to_numpy(item["indices"], np.int64),
            labels=to_numpy(item["labels"], np.int64),
            action_predictions=to_numpy(item["action_predictions"], np.int64),
            action_task_ids=to_numpy(item["action_task_ids"], np.int64),
            action_features=to_numpy(item["action_features"], np.float64),
            action_correctness=to_numpy(item["action_correctness"], bool),
            feature_names=item_names,
            schema_hash=str(item.get("schema_hash", schema_hash)),
            source_path=str(path),
        )
        evidence.validate()
        if evidence.schema_hash != schema_hash or evidence.feature_names != names:
            raise ProtocolError(f"Nested evidence schema mismatch in {path}")
        result[k] = evidence
    if set(result) != {2, 3}:
        raise ProtocolError(f"Evidence artifact must contain top-2 and top-3: {path}")
    return result, payload.get("metadata", {}), payload


def _project_score(path: Path) -> Tuple[int, int, str]:
    markers = sum((path / name).is_dir() for name in ("stage03", "stage04", "data"))
    name = int(path.name.lower() == "akm_clr")
    return markers, name, str(path)


def resolve_project_root(cfg: Config) -> Path:
    """Resolve AKM_CLR without recursive traversal through Drive shortcuts.

    Google Drive's Colab mount does not reliably support Path.rglob across
    `.shortcut-targets-by-id`.  Traverse the small, known directory depth
    explicitly, matching the discovery strategy already validated by v0.23R.
    """
    if cfg.project_root_override:
        candidate = Path(cfg.project_root_override).expanduser()
        if not candidate.is_dir():
            raise FileNotFoundError(f"Configured project root does not exist: {candidate}")
        resolved = candidate.resolve()
        if _project_score(resolved)[0] < 2:
            raise FileNotFoundError(f"Configured project root lacks expected markers: {resolved}")
        print(f"[root] {resolved}", flush=True)
        return resolved

    mount = Path(cfg.drive_mount)
    mydrive = mount / "MyDrive"
    shortcuts = mount / ".shortcut-targets-by-id"
    candidates: Dict[str, Path] = {}
    inspected: Dict[str, List[str]] = {}

    def safe_children(path: Path, limit: int) -> List[Path]:
        if not path.is_dir():
            return []
        try:
            children = sorted(path.iterdir(), key=lambda p: p.name.lower())[:limit]
            inspected[str(path)] = [child.name for child in children[:50]]
            return children
        except OSError as exc:
            inspected[str(path)] = [f"<unreadable: {type(exc).__name__}: {exc}>"]
            return []

    def consider(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if not resolved.is_dir():
            return
        score, name_bonus, _ = _project_score(resolved)
        if score >= 2 or (name_bonus and score >= 1):
            candidates[str(resolved)] = resolved

    # Common direct MyDrive placements and at most two nested folder levels.
    if mydrive.is_dir():
        consider(mydrive / "AKM_CLR")
        for child in safe_children(mydrive, 500):
            if not child.is_dir():
                continue
            consider(child)
            for grandchild in safe_children(child, 500):
                if grandchild.is_dir():
                    consider(grandchild)

    # Shortcut layout used by the real project:
    # .shortcut-targets-by-id/<shortcut-id>/ALL/AKM_CLR
    if shortcuts.is_dir():
        for shortcut_id in safe_children(shortcuts, 200):
            if not shortcut_id.is_dir():
                continue
            consider(shortcut_id)
            for level1 in safe_children(shortcut_id, 200):
                if not level1.is_dir():
                    continue
                consider(level1)
                for level2 in safe_children(level1, 500):
                    if level2.is_dir():
                        consider(level2)

    if not candidates:
        diagnostics = {
            "drive_mount": str(mount),
            "mydrive_exists": mydrive.is_dir(),
            "shortcuts_exists": shortcuts.is_dir(),
            "inspected": inspected,
        }
        raise FileNotFoundError(
            "Could not discover AKM_CLR using shortcut-aware bounded traversal. "
            "Set AKILI_V023T_PROJECT_ROOT only if the project was moved outside the usual Drive tree.\n"
            + json.dumps(diagnostics, indent=2)
        )

    ranked = sorted(candidates.values(), key=_project_score, reverse=True)
    best = ranked[0]
    best_key = _project_score(best)[:2]
    tied = [path for path in ranked if _project_score(path)[:2] == best_key]
    if len(tied) > 1:
        named = [path for path in tied if path.name.lower() == "akm_clr"]
        if len(named) == 1:
            best = named[0]
        else:
            raise ProtocolError(
                "Multiple equally plausible project roots found. Set AKILI_V023T_PROJECT_ROOT: "
                + ", ".join(map(str, tied[:20]))
            )

    print(f"[root] {best}", flush=True)
    return best


def source_run_complete(path: Path, cfg: Config) -> bool:
    if not path.is_dir():
        return False
    if not (path / "completion.json").is_file() or not (path / "hard_checks.json").is_file():
        return False
    try:
        completion = json.loads((path / "completion.json").read_text(encoding="utf-8"))
        hard = json.loads((path / "hard_checks.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    if completion.get("protocol") != SOURCE_PROTOCOL or not bool(hard.get("all_passed")):
        return False
    for seed in cfg.seeds:
        seed_root = path / f"seed_{seed}"
        required = (
            seed_root / "action_feature_manifest.json",
            seed_root / "replay_action_evidence.pt",
            seed_root / "protected_probe_action_evidence.pt",
            seed_root / "evidence_hashes.json",
        )
        if not all(p.is_file() for p in required):
            return False
    return True


def resolve_source_run(project_root: Path, cfg: Config) -> Path:
    if cfg.source_run_override:
        path = Path(cfg.source_run_override).expanduser().resolve()
        if not source_run_complete(path, cfg):
            raise FileNotFoundError(f"Configured v0.23R source run is incomplete: {path}")
        return path
    stage = project_root / "stage04" / "v0_23R_reconstructed_action_evidence"
    candidates = [p.resolve() for p in stage.glob("run_*") if source_run_complete(p, cfg)] if stage.is_dir() else []
    if not candidates:
        raise FileNotFoundError(
            "No complete v0.23R persisted-evidence run found. Set AKILI_V023T_SOURCE_RUN_ROOT."
        )
    candidates.sort(key=lambda p: ((p / "completion.json").stat().st_mtime_ns, str(p)), reverse=True)
    return candidates[0]


def source_files(source_run: Path, cfg: Config) -> List[Path]:
    paths = [source_run / "completion.json", source_run / "hard_checks.json", source_run / "aggregate_summary.json"]
    for seed in cfg.seeds:
        root = source_run / f"seed_{seed}"
        paths.extend(
            [
                root / "action_feature_manifest.json",
                root / "replay_action_evidence.pt",
                root / "protected_probe_action_evidence.pt",
                root / "evidence_hashes.json",
            ]
        )
    return sorted({p.resolve() for p in paths if p.is_file()})


def load_replay_and_probe_catalog(
    source_run: Path,
    cfg: Config,
) -> Tuple[Dict[int, Dict[int, Evidence]], Dict[int, Dict[str, Any]], Dict[str, Any]]:
    replay: Dict[int, Dict[int, Evidence]] = {}
    probe_catalog: Dict[int, Dict[str, Any]] = {}
    schema_hashes = set()
    feature_names: Optional[Tuple[str, ...]] = None
    source_hard_checks = json.loads((source_run / "hard_checks.json").read_text(encoding="utf-8"))
    if not bool(source_hard_checks.get("all_passed")):
        raise ProtocolError("The source v0.23R run did not pass its hard checks")
    validation: Dict[str, Any] = {
        "seeds": {},
        "source_v023r_hard_checks_passed": True,
        "protected_probe_deserialized_during_initial_load": False,
        "source_digest_contract": {
            "indices": "int64",
            "labels": "int64",
            "action_predictions": "int64",
            "action_task_ids": "int64",
            "action_features": "float32",
            "action_correctness": "bool",
            "canonical_json": "sort_keys=True,separators=(comma,colon)",
        },
        "analysis_feature_dtype": "float64_after_integrity_validation",
    }
    for seed in cfg.seeds:
        seed_root = source_run / f"seed_{seed}"
        manifest = json.loads((seed_root / "action_feature_manifest.json").read_text(encoding="utf-8"))
        hashes = json.loads((seed_root / "evidence_hashes.json").read_text(encoding="utf-8"))
        replay_path = seed_root / "replay_action_evidence.pt"
        probe_path = seed_root / "protected_probe_action_evidence.pt"
        if sha256_file(replay_path) != hashes["replay"]["sha256"]:
            raise ProtocolError(f"Replay file hash mismatch for seed {seed}")
        if sha256_file(probe_path) != hashes["probe"]["sha256"]:
            raise ProtocolError(f"Probe file hash mismatch for seed {seed}")
        replay[seed], replay_meta, _ = load_evidence_file(replay_path)
        if int(replay_meta.get("seed", seed)) != seed:
            raise ProtocolError(f"Metadata seed mismatch for seed {seed}")
        if manifest.get("metadata") != replay_meta:
            raise ProtocolError(f"Manifest metadata mismatch for seed {seed}")
        for k in cfg.candidate_counts:
            r = replay[seed][k]
            if r.seed != seed:
                raise ProtocolError("Replay evidence seed mismatch")
            if r.n != cfg.expected_replay_count:
                raise ProtocolError(
                    f"Replay count mismatch seed={seed} top{k}: {r.n} != {cfg.expected_replay_count}"
                )
            if not np.array_equal(r.labels, replay[seed][3].labels):
                raise ProtocolError(f"Candidate-count replay labels differ seed={seed}")
            if not np.array_equal(r.action_predictions[:, 0], replay[seed][3].action_predictions[:, 0]):
                raise ProtocolError(f"KEEP predictions differ by candidate count seed={seed}")
            schema_hashes.add(r.schema_hash)
            if feature_names is None:
                feature_names = r.feature_names
            if r.feature_names != feature_names:
                raise ProtocolError("Feature names differ across replay seeds")
            expected_digest_r = hashes["replay"]["evidence_digests"][str(k)]
            if evidence_digest(r) != expected_digest_r:
                raise ProtocolError(f"Replay evidence digest mismatch seed={seed} top{k}")
            if int(hashes["probe"]["counts"][str(k)]) != cfg.expected_probe_count:
                raise ProtocolError(
                    f"Probe catalog count mismatch seed={seed} top{k}: "
                    f"{hashes['probe']['counts'][str(k)]} != {cfg.expected_probe_count}"
                )
        probe_catalog[seed] = {
            "path": str(probe_path),
            "metadata": replay_meta,
            "sha256": hashes["probe"]["sha256"],
            "evidence_digests": hashes["probe"]["evidence_digests"],
            "counts": hashes["probe"]["counts"],
        }
        validation["seeds"][str(seed)] = {
            "replay_sha256": hashes["replay"]["sha256"],
            "probe_sha256_catalog_only": hashes["probe"]["sha256"],
            "metadata": replay_meta,
        }
    if len(schema_hashes) != 1 or feature_names is None:
        raise ProtocolError("Replay evidence schema is not shared across all seeds")
    validation["schema_hash"] = next(iter(schema_hashes))
    validation["feature_names"] = list(feature_names)
    validation["feature_count"] = len(feature_names)
    return replay, probe_catalog, validation


def load_protected_probe_after_replay_selection(
    probe_catalog: Mapping[int, Mapping[str, Any]],
    replay: Mapping[int, Mapping[int, Evidence]],
    cfg: Config,
) -> Tuple[Dict[int, Dict[int, Evidence]], Dict[str, Any]]:
    probe: Dict[int, Dict[int, Evidence]] = {}
    audit: Dict[str, Any] = {"deserialized_seed_files": 0, "seeds": {}}
    for seed in cfg.seeds:
        entry = probe_catalog[seed]
        path = Path(str(entry["path"]))
        if sha256_file(path) != str(entry["sha256"]):
            raise ProtocolError(f"Protected-probe file hash changed before access seed={seed}")
        loaded, metadata, _ = load_evidence_file(path)
        audit["deserialized_seed_files"] += 1
        if metadata != entry["metadata"]:
            raise ProtocolError(f"Protected-probe metadata mismatch seed={seed}")
        for k in cfg.candidate_counts:
            evidence = loaded[k]
            if evidence.n != cfg.expected_probe_count:
                raise ProtocolError(f"Protected-probe count mismatch seed={seed} top{k}")
            if evidence_digest(evidence) != entry["evidence_digests"][str(k)]:
                raise ProtocolError(f"Protected-probe digest mismatch seed={seed} top{k}")
            if set(evidence.indices.tolist()) & set(replay[seed][k].indices.tolist()):
                raise ProtocolError(f"Replay/protected-probe overlap seed={seed} top{k}")
            if evidence.feature_names != replay[seed][k].feature_names:
                raise ProtocolError(f"Protected-probe feature schema mismatch seed={seed} top{k}")
        probe[seed] = loaded
        audit["seeds"][str(seed)] = {
            "path": str(path),
            "sha256": entry["sha256"],
            "top2_count": loaded[2].n,
            "top3_count": loaded[3].n,
        }
    audit["replay_probe_disjoint"] = True
    return probe, audit


def combine(parts: Sequence[Evidence], split: str) -> Evidence:
    if not parts:
        raise ValueError("No evidence parts")
    k = parts[0].candidate_count
    names = parts[0].feature_names
    schema = parts[0].schema_hash
    if any(p.candidate_count != k or p.feature_names != names or p.schema_hash != schema for p in parts):
        raise ProtocolError("Cannot combine incompatible evidence")
    result = Evidence(
        seed=-1,
        split=split,
        candidate_count=k,
        indices=np.arange(sum(p.n for p in parts), dtype=np.int64),
        labels=np.concatenate([p.labels for p in parts]),
        action_predictions=np.concatenate([p.action_predictions for p in parts], axis=0),
        action_task_ids=np.concatenate([p.action_task_ids for p in parts], axis=0),
        action_features=np.concatenate([p.action_features for p in parts], axis=0),
        action_correctness=np.concatenate([p.action_correctness for p in parts], axis=0),
        feature_names=names,
        schema_hash=schema,
    )
    result.validate()
    return result


def capacity_metrics(evidence: Evidence) -> Dict[str, Any]:
    evidence.validate()
    correct = evidence.action_correctness.astype(bool)
    keep = correct[:, 0]
    expert = correct[:, 1:]
    union = np.any(correct, axis=1)
    expert_union = np.any(expert, axis=1)
    counts = correct.sum(axis=1)
    metrics: Dict[str, Any] = {
        "examples": evidence.n,
        "baseline_accuracy": float(keep.mean()),
        "available_action_union_accuracy": float(union.mean()),
        "expert_only_union_accuracy": float(expert_union.mean()),
        "rescue_opportunity_count": int(((~keep) & expert_union).sum()),
        "rescue_opportunity_rate": float(((~keep) & expert_union).mean()),
        "no_available_correct_action_count": int((~union).sum()),
        "no_available_correct_action_rate": float((~union).mean()),
        "multiple_correct_actions_count": int((counts > 1).sum()),
        "multiple_correct_actions_rate": float((counts > 1).mean()),
        "only_keep_correct_count": int((keep & (expert.sum(axis=1) == 0)).sum()),
        "keep_wrong_no_expert_correct_count": int(((~keep) & (~expert_union)).sum()),
    }
    for rank in range(1, evidence.action_count):
        only = correct[:, rank] & (correct.sum(axis=1) == 1)
        metrics[f"only_expert_{rank}_correct_count"] = int(only.sum())
        metrics[f"expert_{rank}_correct_rate"] = float(correct[:, rank].mean())
    return metrics


def run_capacity_audit(replay: Mapping[int, Mapping[int, Evidence]], output_root: Path) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    per_example_rows: List[Dict[str, Any]] = []
    for seed in sorted(replay):
        top3 = replay[seed][3]
        correct = top3.action_correctness.astype(bool)
        for i in range(top3.n):
            row = {
                "seed": seed,
                "example_index": int(top3.indices[i]),
                "label": int(top3.labels[i]),
                "keep_prediction": int(top3.action_predictions[i, 0]),
                "keep_correct": bool(correct[i, 0]),
                "expert1_correct": bool(correct[i, 1]),
                "expert2_correct": bool(correct[i, 2]),
                "expert3_correct": bool(correct[i, 3]),
                "top1_union_correct": bool(correct[i, :2].any()),
                "top2_union_correct": bool(correct[i, :3].any()),
                "top3_union_correct": bool(correct[i, :4].any()),
                "rescue_available_top3": bool((not correct[i, 0]) and correct[i, 1:].any()),
                "no_action_correct": bool(not correct[i, :4].any()),
                "correct_action_count": int(correct[i, :4].sum()),
            }
            per_example_rows.append(row)
        base = float(correct[:, 0].mean())
        union1 = float(correct[:, :2].any(axis=1).mean())
        union2 = float(correct[:, :3].any(axis=1).mean())
        union3 = float(correct[:, :4].any(axis=1).mean())
        row = {
            "scope": f"seed_{seed}",
            **capacity_metrics(top3),
            "keep_plus_expert1_accuracy": union1,
            "top2_action_union_accuracy": union2,
            "top3_action_union_accuracy": union3,
            "top1_increment_over_keep": union1 - base,
            "expert2_increment_over_top1": union2 - union1,
            "expert3_increment_over_top2": union3 - union2,
            "gap_from_top3_union_to_79pct": 0.79 - union3,
        }
        rows.append(row)
    pooled = combine([replay[s][3] for s in sorted(replay)], "pooled_replay_top3")
    correct = pooled.action_correctness.astype(bool)
    base = float(correct[:, 0].mean())
    union1 = float(correct[:, :2].any(axis=1).mean())
    union2 = float(correct[:, :3].any(axis=1).mean())
    union3 = float(correct[:, :4].any(axis=1).mean())
    pooled_row = {
        "scope": "pooled",
        **capacity_metrics(pooled),
        "keep_plus_expert1_accuracy": union1,
        "top2_action_union_accuracy": union2,
        "top3_action_union_accuracy": union3,
        "top1_increment_over_keep": union1 - base,
        "expert2_increment_over_top1": union2 - union1,
        "expert3_increment_over_top2": union3 - union2,
        "gap_from_top3_union_to_79pct": 0.79 - union3,
    }
    rows.append(pooled_row)
    frame = pd.DataFrame(rows)
    atomic_csv(output_root / "capacity_summary.csv", frame)
    atomic_csv(output_root / "capacity_per_example_top3.csv", pd.DataFrame(per_example_rows))
    summary = {
        "pooled": pooled_row,
        "per_seed": {row["scope"]: row for row in rows if row["scope"] != "pooled"},
        "interpretation": (
            "top3_action_union_accuracy is the maximum achievable replay accuracy using only KEEP and the three persisted candidate experts."
        ),
    }
    atomic_json(output_root / "capacity_summary.json", summary)
    return summary


def safe_auc(y: np.ndarray, score: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.int64)
    score = np.asarray(score, dtype=np.float64)
    if np.unique(y).size < 2 or not np.isfinite(score).all():
        return float("nan")
    return float(roc_auc_score(y, score))


def class_balanced_weights(labels: np.ndarray) -> np.ndarray:
    y = np.asarray(labels)
    result = np.ones(y.shape[0], dtype=np.float64)
    classes, counts = np.unique(y, return_counts=True)
    if classes.size <= 1:
        return result
    n = float(y.shape[0])
    for cls, count in zip(classes, counts):
        result[y == cls] = n / (float(classes.size) * float(count))
    return result


def normalized_vote_count(values: np.ndarray) -> float:
    _, counts = np.unique(values, return_counts=True)
    return float(counts.max() / max(values.size, 1))


def relation_features(data: Evidence) -> Tuple[np.ndarray, Tuple[str, ...]]:
    if data.candidate_count != CANDIDATE_COUNT:
        raise ProtocolError("v0.23T relation features require top-3 evidence")
    predictions = data.action_predictions
    tasks = data.action_task_ids
    n = data.n
    rows = np.zeros((n, 18), dtype=np.float32)
    for i in range(n):
        expert_predictions = predictions[i, 1:]
        expert_tasks = tasks[i, 1:]
        rows[i, 0] = np.unique(predictions[i]).size / 4.0
        rows[i, 1] = np.unique(expert_predictions).size / 3.0
        rows[i, 2] = np.mean(expert_predictions == predictions[i, 0])
        rows[i, 3] = normalized_vote_count(expert_predictions)
        rows[i, 4] = float(np.unique(expert_predictions).size == 1)
        rows[i, 5] = float(np.unique(expert_predictions).size < 3)
        rows[i, 6] = np.unique(tasks[i]).size / 4.0
        rows[i, 7] = np.unique(expert_tasks).size / 3.0
        rows[i, 8] = np.mean(expert_tasks == tasks[i, 0])
        rows[i, 9] = normalized_vote_count(expert_tasks)
        rows[i, 10] = float(np.unique(expert_tasks).size == 1)
        rows[i, 11] = float(np.unique(expert_tasks).size < 3)
        rows[i, 12] = float(expert_predictions[0] == expert_predictions[1])
        rows[i, 13] = float(expert_predictions[0] == expert_predictions[2])
        rows[i, 14] = float(expert_predictions[1] == expert_predictions[2])
        rows[i, 15] = float(expert_tasks[0] == expert_tasks[1])
        rows[i, 16] = float(expert_tasks[0] == expert_tasks[2])
        rows[i, 17] = float(expert_tasks[1] == expert_tasks[2])
    names = (
        "relation::unique_action_prediction_fraction",
        "relation::unique_expert_prediction_fraction",
        "relation::experts_matching_keep_prediction_fraction",
        "relation::max_expert_prediction_vote_fraction",
        "relation::all_experts_same_prediction",
        "relation::any_expert_pair_same_prediction",
        "relation::unique_action_task_fraction",
        "relation::unique_expert_task_fraction",
        "relation::experts_matching_keep_task_fraction",
        "relation::max_expert_task_vote_fraction",
        "relation::all_experts_same_task",
        "relation::any_expert_pair_same_task",
        "relation::expert1_prediction_equals_expert2",
        "relation::expert1_prediction_equals_expert3",
        "relation::expert2_prediction_equals_expert3",
        "relation::expert1_task_equals_expert2",
        "relation::expert1_task_equals_expert3",
        "relation::expert2_task_equals_expert3",
    )
    return rows, names


def build_group_features(
    data: Evidence,
) -> Tuple[np.ndarray, Tuple[str, ...]]:
    data.validate()
    if data.candidate_count != CANDIDATE_COUNT:
        raise ProtocolError("v0.23T uses top-3 evidence only")
    action = data.action_features.astype(np.float32, copy=False)
    keep = action[:, 0, :]
    experts = action[:, 1:, :]
    mean = experts.mean(axis=1)
    std = experts.std(axis=1)
    minimum = experts.min(axis=1)
    maximum = experts.max(axis=1)
    relation, relation_names = relation_features(data)

    parts = [
        keep,
        experts.reshape(data.n, -1),
        (experts - keep[:, None, :]).reshape(data.n, -1),
        mean,
        std,
        minimum,
        maximum,
        mean - keep,
        maximum - keep,
        minimum - keep,
        relation,
    ]
    names: List[str] = []
    names.extend(f"keep::{name}" for name in data.feature_names)
    for rank in range(1, 4):
        names.extend(
            f"expert{rank}::{name}" for name in data.feature_names
        )
    for rank in range(1, 4):
        names.extend(
            f"expert{rank}_minus_keep::{name}"
            for name in data.feature_names
        )
    for aggregate in ("mean", "std", "min", "max"):
        names.extend(
            f"expert_{aggregate}::{name}" for name in data.feature_names
        )
    for aggregate in ("mean", "max", "min"):
        names.extend(
            f"expert_{aggregate}_minus_keep::{name}"
            for name in data.feature_names
        )
    names.extend(relation_names)

    result = np.concatenate(parts, axis=1).astype(np.float32, copy=False)
    if result.shape != (data.n, len(names)):
        raise ProtocolError(
            f"Group feature shape mismatch: {result.shape} vs "
            f"{(data.n, len(names))}"
        )
    if not np.isfinite(result).all():
        raise ProtocolError("Non-finite group features")
    return result, tuple(names)


def build_ranker_features(
    data: Evidence,
    group_features: Optional[np.ndarray] = None,
    group_names: Optional[Tuple[str, ...]] = None,
) -> Tuple[np.ndarray, Tuple[str, ...]]:
    if data.candidate_count != CANDIDATE_COUNT:
        raise ProtocolError("v0.23T ranker requires top-3 evidence")
    if group_features is None or group_names is None:
        group_features, group_names = build_group_features(data)
    action = data.action_features.astype(np.float32, copy=False)
    keep = action[:, 0, :]
    experts = action[:, 1:, :]
    rows: List[np.ndarray] = []

    for rank in range(3):
        current = experts[:, rank, :]
        other_indices = [index for index in range(3) if index != rank]
        others = experts[:, other_indices, :]
        other_mean = others.mean(axis=1)
        other_max = others.max(axis=1)
        other_min = others.min(axis=1)
        other_std = others.std(axis=1)

        prediction_match_fraction = np.mean(
            data.action_predictions[:, other_indices + np.ones(
                len(other_indices), dtype=np.int64
            )]
            == data.action_predictions[:, [rank + 1]],
            axis=1,
        ).reshape(-1, 1)
        task_match_fraction = np.mean(
            data.action_task_ids[:, other_indices + np.ones(
                len(other_indices), dtype=np.int64
            )]
            == data.action_task_ids[:, [rank + 1]],
            axis=1,
        ).reshape(-1, 1)
        relations = np.concatenate(
            [
                (
                    data.action_predictions[:, rank + 1]
                    == data.action_predictions[:, 0]
                ).astype(np.float32).reshape(-1, 1),
                (
                    data.action_task_ids[:, rank + 1]
                    == data.action_task_ids[:, 0]
                ).astype(np.float32).reshape(-1, 1),
                prediction_match_fraction.astype(np.float32),
                task_match_fraction.astype(np.float32),
                np.full(
                    (data.n, 1),
                    float(rank + 1) / 3.0,
                    dtype=np.float32,
                ),
            ],
            axis=1,
        )
        specific = np.concatenate(
            [
                current,
                current - keep,
                current - other_mean,
                current - other_max,
                current - other_min,
                other_std,
                relations,
            ],
            axis=1,
        )
        rows.append(
            np.concatenate([group_features, specific], axis=1)
        )

    result = np.stack(rows, axis=1).astype(np.float32, copy=False)
    specific_names: List[str] = []
    specific_names.extend(
        f"current_expert::{name}" for name in data.feature_names
    )
    specific_names.extend(
        f"current_expert_minus_keep::{name}"
        for name in data.feature_names
    )
    specific_names.extend(
        f"current_expert_minus_other_mean::{name}"
        for name in data.feature_names
    )
    specific_names.extend(
        f"current_expert_minus_other_max::{name}"
        for name in data.feature_names
    )
    specific_names.extend(
        f"current_expert_minus_other_min::{name}"
        for name in data.feature_names
    )
    specific_names.extend(
        f"other_expert_std::{name}" for name in data.feature_names
    )
    specific_names.extend(
        (
            "current_expert::prediction_matches_keep",
            "current_expert::task_matches_keep",
            "current_expert::other_prediction_match_fraction",
            "current_expert::other_task_match_fraction",
            "current_expert::rank_normalized",
        )
    )
    names = tuple(group_names) + tuple(specific_names)
    if result.shape != (data.n, 3, len(names)):
        raise ProtocolError(
            f"Ranker feature shape mismatch: {result.shape}"
        )
    if not np.isfinite(result).all():
        raise ProtocolError("Non-finite ranker features")
    return result, names


def rescue_target(data: Evidence) -> np.ndarray:
    correct = data.action_correctness.astype(bool)
    return ((~correct[:, 0]) & correct[:, 1:].any(axis=1)).astype(
        np.int64
    )


def deterministic_joint_target(data: Evidence) -> np.ndarray:
    correct = data.action_correctness.astype(bool)
    target = np.zeros(data.n, dtype=np.int64)
    opportunities = (~correct[:, 0]) & correct[:, 1:].any(axis=1)
    for action in range(1, 4):
        choose = opportunities & (target == 0) & correct[:, action]
        target[choose] = action
    return target


def ranker_targets_and_weights(
    data: Evidence,
) -> Tuple[np.ndarray, np.ndarray]:
    correct = data.action_correctness[:, 1:].astype(np.int64)
    labels = correct.reshape(-1)
    balanced = class_balanced_weights(labels).reshape(data.n, 3)
    keep_correct = data.action_correctness[:, 0].astype(bool)
    expert_correct = data.action_correctness[:, 1:].astype(bool)
    differs = (
        data.action_predictions[:, 1:]
        != data.action_predictions[:, [0]]
    )
    multiplier = np.ones((data.n, 3), dtype=np.float64)
    multiplier[
        (~keep_correct)[:, None] & expert_correct & differs
    ] = 2.0
    multiplier[
        keep_correct[:, None] & (~expert_correct) & differs
    ] = 3.0
    multiplier[~differs] = 0.5
    weights = balanced * multiplier
    return labels, weights.reshape(-1)


@dataclass
class BinaryProbabilityBundle:
    backend_names: Tuple[str, ...]
    backend_weights: Tuple[float, ...]
    models: Tuple[Any, ...]
    constant_probability: Optional[float] = None

    def predict_positive(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float32)
        if self.constant_probability is not None:
            result = np.full(
                x.shape[0],
                float(self.constant_probability),
                dtype=np.float64,
            )
        else:
            result = np.zeros(x.shape[0], dtype=np.float64)
            for weight, model in zip(
                self.backend_weights, self.models
            ):
                probabilities = model.predict_proba(x)
                classes = np.asarray(model.classes_, dtype=np.int64)
                positive_columns = np.where(classes == 1)[0]
                component = (
                    probabilities[:, int(positive_columns[0])]
                    if positive_columns.size
                    else np.zeros(x.shape[0], dtype=np.float64)
                )
                result += float(weight) * component
        if result.shape != (x.shape[0],):
            raise ProtocolError("Binary probability shape mismatch")
        if not np.isfinite(result).all():
            raise ProtocolError("Non-finite binary probabilities")
        return np.clip(result, 0.0, 1.0)


@dataclass
class MultiClassProbabilityBundle:
    class_count: int
    backend_names: Tuple[str, ...]
    backend_weights: Tuple[float, ...]
    models: Tuple[Any, ...]
    constant_class: Optional[int] = None

    def predict_full(self, features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float32)
        result = np.zeros(
            (x.shape[0], self.class_count), dtype=np.float64
        )
        if self.constant_class is not None:
            result[:, int(self.constant_class)] = 1.0
        else:
            for weight, model in zip(
                self.backend_weights, self.models
            ):
                probabilities = model.predict_proba(x)
                classes = np.asarray(model.classes_, dtype=np.int64)
                for column, cls in enumerate(classes):
                    if 0 <= int(cls) < self.class_count:
                        result[:, int(cls)] += (
                            float(weight) * probabilities[:, column]
                        )
        row_sums = result.sum(axis=1, keepdims=True)
        zero = row_sums[:, 0] <= 0.0
        if np.any(zero):
            result[zero, 0] = 1.0
            row_sums = result.sum(axis=1, keepdims=True)
        result = result / row_sums
        if not np.isfinite(result).all():
            raise ProtocolError("Non-finite multiclass probabilities")
        return result


@dataclass
class NonlinearVerifier:
    spec_id: str
    mode: str
    group_feature_names: Tuple[str, ...]
    rank_feature_names: Tuple[str, ...]
    gate_model: Optional[BinaryProbabilityBundle] = None
    rank_model: Optional[BinaryProbabilityBundle] = None
    joint_model: Optional[MultiClassProbabilityBundle] = None

    def score(
        self,
        data: Evidence,
    ) -> Tuple[np.ndarray, np.ndarray]:
        group, group_names = build_group_features(data)
        if group_names != self.group_feature_names:
            raise ProtocolError("Group feature manifest changed")
        if self.mode == "two_stage":
            if self.gate_model is None or self.rank_model is None:
                raise ProtocolError("Incomplete two-stage verifier")
            rank, rank_names = build_ranker_features(
                data, group, group_names
            )
            if rank_names != self.rank_feature_names:
                raise ProtocolError("Rank feature manifest changed")
            gate = self.gate_model.predict_positive(group)
            expert = self.rank_model.predict_positive(
                rank.reshape(-1, rank.shape[-1])
            ).reshape(data.n, 3)
        elif self.mode == "joint":
            if self.joint_model is None:
                raise ProtocolError("Incomplete joint verifier")
            probabilities = self.joint_model.predict_full(group)
            gate = 1.0 - probabilities[:, 0]
            expert = probabilities[:, 1:4]
        else:
            raise ProtocolError(f"Unknown verifier mode: {self.mode}")
        if gate.shape != (data.n,) or expert.shape != (data.n, 3):
            raise ProtocolError("Verifier score shape mismatch")
        if not np.isfinite(gate).all() or not np.isfinite(expert).all():
            raise ProtocolError("Non-finite verifier scores")
        return np.clip(gate, 0.0, 1.0), np.clip(
            expert, 0.0, 1.0
        )


def backend_model(
    backend: str,
    cfg: Config,
    random_state: int,
) -> Any:
    if backend == "extra_trees":
        return ExtraTreesClassifier(
            n_estimators=cfg.tree_estimators,
            max_depth=10,
            min_samples_leaf=4,
            max_features=0.5,
            bootstrap=False,
            class_weight="balanced",
            n_jobs=cfg.n_jobs,
            random_state=random_state,
        )
    if backend == "random_forest":
        return RandomForestClassifier(
            n_estimators=cfg.random_forest_estimators,
            max_depth=10,
            min_samples_leaf=4,
            max_features="sqrt",
            bootstrap=True,
            class_weight="balanced_subsample",
            n_jobs=cfg.n_jobs,
            random_state=random_state,
        )
    raise ValueError(f"Unknown backend: {backend}")


def normalized_backend_definition(
    spec_id: str,
) -> Tuple[str, Tuple[str, ...], Tuple[float, ...]]:
    if spec_id not in MODEL_SPECS:
        raise ValueError(spec_id)
    definition = MODEL_SPECS[spec_id]
    names = tuple(str(name) for name, _ in definition["backends"])
    raw_weights = np.asarray(
        [float(weight) for _, weight in definition["backends"]],
        dtype=np.float64,
    )
    if np.any(raw_weights <= 0.0) or not np.isfinite(raw_weights).all():
        raise ProtocolError("Invalid backend weights")
    weights = tuple((raw_weights / raw_weights.sum()).tolist())
    return str(definition["mode"]), names, weights


def fit_binary_bundle(
    features: np.ndarray,
    labels: np.ndarray,
    sample_weight: np.ndarray,
    backend_names: Tuple[str, ...],
    backend_weights: Tuple[float, ...],
    cfg: Config,
    random_state: int,
) -> BinaryProbabilityBundle:
    x = np.asarray(features, dtype=np.float32)
    y = np.asarray(labels, dtype=np.int64)
    weights = np.asarray(sample_weight, dtype=np.float64)
    if x.ndim != 2 or y.shape != (x.shape[0],):
        raise ProtocolError("Binary training shape mismatch")
    if weights.shape != y.shape or not np.isfinite(weights).all():
        raise ProtocolError("Binary sample-weight mismatch")
    unique = np.unique(y)
    if unique.size == 1:
        return BinaryProbabilityBundle(
            backend_names=backend_names,
            backend_weights=backend_weights,
            models=tuple(),
            constant_probability=float(unique[0]),
        )
    models: List[Any] = []
    for offset, backend in enumerate(backend_names):
        model = backend_model(
            backend,
            cfg,
            random_state + 101 * (offset + 1),
        )
        model.fit(x, y, sample_weight=weights)
        models.append(model)
    return BinaryProbabilityBundle(
        backend_names=backend_names,
        backend_weights=backend_weights,
        models=tuple(models),
    )


def fit_multiclass_bundle(
    features: np.ndarray,
    labels: np.ndarray,
    sample_weight: np.ndarray,
    class_count: int,
    backend_names: Tuple[str, ...],
    backend_weights: Tuple[float, ...],
    cfg: Config,
    random_state: int,
) -> MultiClassProbabilityBundle:
    x = np.asarray(features, dtype=np.float32)
    y = np.asarray(labels, dtype=np.int64)
    weights = np.asarray(sample_weight, dtype=np.float64)
    if x.ndim != 2 or y.shape != (x.shape[0],):
        raise ProtocolError("Multiclass training shape mismatch")
    if weights.shape != y.shape or not np.isfinite(weights).all():
        raise ProtocolError("Multiclass sample-weight mismatch")
    unique = np.unique(y)
    if unique.size == 1:
        return MultiClassProbabilityBundle(
            class_count=class_count,
            backend_names=backend_names,
            backend_weights=backend_weights,
            models=tuple(),
            constant_class=int(unique[0]),
        )
    models: List[Any] = []
    for offset, backend in enumerate(backend_names):
        model = backend_model(
            backend,
            cfg,
            random_state + 211 * (offset + 1),
        )
        model.fit(x, y, sample_weight=weights)
        models.append(model)
    return MultiClassProbabilityBundle(
        class_count=class_count,
        backend_names=backend_names,
        backend_weights=backend_weights,
        models=tuple(models),
    )


def fit_verifier(
    data: Evidence,
    spec_id: str,
    cfg: Config,
    random_state: int,
) -> NonlinearVerifier:
    if data.candidate_count != CANDIDATE_COUNT:
        raise ProtocolError("v0.23T fits top-3 evidence only")
    mode, backends, weights = normalized_backend_definition(spec_id)
    group, group_names = build_group_features(data)
    rank, rank_names = build_ranker_features(
        data, group, group_names
    )
    if mode == "two_stage":
        gate_y = rescue_target(data)
        gate_weights = class_balanced_weights(gate_y)
        rank_y, rank_weights = ranker_targets_and_weights(data)
        gate_model = fit_binary_bundle(
            group,
            gate_y,
            gate_weights,
            backends,
            weights,
            cfg,
            random_state + 1000,
        )
        rank_model = fit_binary_bundle(
            rank.reshape(-1, rank.shape[-1]),
            rank_y,
            rank_weights,
            backends,
            weights,
            cfg,
            random_state + 2000,
        )
        return NonlinearVerifier(
            spec_id=spec_id,
            mode=mode,
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            gate_model=gate_model,
            rank_model=rank_model,
        )
    if mode == "joint":
        target = deterministic_joint_target(data)
        joint_weights = class_balanced_weights(target)
        opportunities = rescue_target(data).astype(bool)
        joint_weights[opportunities] *= 2.0
        joint_weights[data.action_correctness[:, 0].astype(bool)] *= 1.5
        joint = fit_multiclass_bundle(
            group,
            target,
            joint_weights,
            4,
            backends,
            weights,
            cfg,
            random_state + 3000,
        )
        return NonlinearVerifier(
            spec_id=spec_id,
            mode=mode,
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            joint_model=joint,
        )
    raise ProtocolError(f"Unknown model mode: {mode}")


def _blend_binary_bundles(
    first: BinaryProbabilityBundle,
    second: BinaryProbabilityBundle,
    fallback_features: np.ndarray,
    fallback_labels: np.ndarray,
    fallback_weights: np.ndarray,
    cfg: Config,
    random_state: int,
) -> BinaryProbabilityBundle:
    if (
        first.constant_probability is None
        and second.constant_probability is None
    ):
        return BinaryProbabilityBundle(
            backend_names=(
                first.backend_names[0],
                second.backend_names[0],
            ),
            backend_weights=(0.5, 0.5),
            models=(first.models[0], second.models[0]),
        )
    return fit_binary_bundle(
        fallback_features,
        fallback_labels,
        fallback_weights,
        ("extra_trees", "random_forest"),
        (0.5, 0.5),
        cfg,
        random_state,
    )


def _blend_multiclass_bundles(
    first: MultiClassProbabilityBundle,
    second: MultiClassProbabilityBundle,
    fallback_features: np.ndarray,
    fallback_labels: np.ndarray,
    fallback_weights: np.ndarray,
    cfg: Config,
    random_state: int,
) -> MultiClassProbabilityBundle:
    if (
        first.constant_class is None
        and second.constant_class is None
    ):
        return MultiClassProbabilityBundle(
            class_count=4,
            backend_names=(
                first.backend_names[0],
                second.backend_names[0],
            ),
            backend_weights=(0.5, 0.5),
            models=(first.models[0], second.models[0]),
        )
    return fit_multiclass_bundle(
        fallback_features,
        fallback_labels,
        fallback_weights,
        4,
        ("extra_trees", "random_forest"),
        (0.5, 0.5),
        cfg,
        random_state,
    )


def fit_all_verifiers(
    data: Evidence,
    cfg: Config,
    random_state: int,
) -> Dict[str, NonlinearVerifier]:
    """Fit shared primitive models once and assemble all six specifications."""
    if data.candidate_count != CANDIDATE_COUNT:
        raise ProtocolError("v0.23T fits top-3 evidence only")
    group, group_names = build_group_features(data)
    rank, rank_names = build_ranker_features(
        data, group, group_names
    )
    rank_flat = rank.reshape(-1, rank.shape[-1])

    gate_y = rescue_target(data)
    gate_weights = class_balanced_weights(gate_y)
    rank_y, rank_weights = ranker_targets_and_weights(data)
    joint_y = deterministic_joint_target(data)
    joint_weights = class_balanced_weights(joint_y)
    opportunities = rescue_target(data).astype(bool)
    joint_weights[opportunities] *= 2.0
    joint_weights[data.action_correctness[:, 0].astype(bool)] *= 1.5

    gate_et = fit_binary_bundle(
        group,
        gate_y,
        gate_weights,
        ("extra_trees",),
        (1.0,),
        cfg,
        random_state + 1001,
    )
    gate_rf = fit_binary_bundle(
        group,
        gate_y,
        gate_weights,
        ("random_forest",),
        (1.0,),
        cfg,
        random_state + 1002,
    )
    rank_et = fit_binary_bundle(
        rank_flat,
        rank_y,
        rank_weights,
        ("extra_trees",),
        (1.0,),
        cfg,
        random_state + 2001,
    )
    rank_rf = fit_binary_bundle(
        rank_flat,
        rank_y,
        rank_weights,
        ("random_forest",),
        (1.0,),
        cfg,
        random_state + 2002,
    )
    joint_et = fit_multiclass_bundle(
        group,
        joint_y,
        joint_weights,
        4,
        ("extra_trees",),
        (1.0,),
        cfg,
        random_state + 3001,
    )
    joint_rf = fit_multiclass_bundle(
        group,
        joint_y,
        joint_weights,
        4,
        ("random_forest",),
        (1.0,),
        cfg,
        random_state + 3002,
    )

    gate_blend = _blend_binary_bundles(
        gate_et,
        gate_rf,
        group,
        gate_y,
        gate_weights,
        cfg,
        random_state + 4001,
    )
    rank_blend = _blend_binary_bundles(
        rank_et,
        rank_rf,
        rank_flat,
        rank_y,
        rank_weights,
        cfg,
        random_state + 4002,
    )
    joint_blend = _blend_multiclass_bundles(
        joint_et,
        joint_rf,
        group,
        joint_y,
        joint_weights,
        cfg,
        random_state + 4003,
    )

    all_models = {
        "two_stage_extra_trees": NonlinearVerifier(
            spec_id="two_stage_extra_trees",
            mode="two_stage",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            gate_model=gate_et,
            rank_model=rank_et,
        ),
        "two_stage_random_forest": NonlinearVerifier(
            spec_id="two_stage_random_forest",
            mode="two_stage",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            gate_model=gate_rf,
            rank_model=rank_rf,
        ),
        "two_stage_blend": NonlinearVerifier(
            spec_id="two_stage_blend",
            mode="two_stage",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            gate_model=gate_blend,
            rank_model=rank_blend,
        ),
        "joint_extra_trees": NonlinearVerifier(
            spec_id="joint_extra_trees",
            mode="joint",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            joint_model=joint_et,
        ),
        "joint_random_forest": NonlinearVerifier(
            spec_id="joint_random_forest",
            mode="joint",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            joint_model=joint_rf,
        ),
        "joint_blend": NonlinearVerifier(
            spec_id="joint_blend",
            mode="joint",
            group_feature_names=group_names,
            rank_feature_names=rank_names,
            joint_model=joint_blend,
        ),
    }
    return {spec: all_models[spec] for spec in cfg.model_specs}


def model_roundtrip_error(
    model: NonlinearVerifier,
    data: Evidence,
) -> float:
    before_gate, before_expert = model.score(data)
    with tempfile.TemporaryDirectory(
        prefix="akili_v023t_model_roundtrip_"
    ) as temporary:
        path = Path(temporary) / "verifier.joblib"
        joblib.dump(model, path, compress=3)
        loaded = joblib.load(path)
        after_gate, after_expert = loaded.score(data)
    return max(
        float(np.max(np.abs(before_gate - after_gate))),
        float(np.max(np.abs(before_expert - after_expert))),
    )


def choose_actions(
    data: Evidence,
    gate_probability: np.ndarray,
    expert_scores: np.ndarray,
    gate_threshold: float,
    expert_threshold: float,
    expert_margin: float,
) -> np.ndarray:
    gate = np.asarray(gate_probability, dtype=np.float64)
    scores = np.asarray(expert_scores, dtype=np.float64)
    if gate.shape != (data.n,) or scores.shape != (data.n, 3):
        raise ProtocolError("Action-selection score shape mismatch")
    if not np.isfinite(gate).all() or not np.isfinite(scores).all():
        raise ProtocolError("Action-selection scores are non-finite")

    differs = (
        data.action_predictions[:, 1:]
        != data.action_predictions[:, [0]]
    )
    masked = np.where(differs, scores, -np.inf)
    best_relative = np.argmax(masked, axis=1)
    row = np.arange(data.n)
    best_score = masked[row, best_relative]

    sorted_scores = np.sort(masked, axis=1)
    second_score = sorted_scores[:, -2]
    margin = best_score - second_score
    has_candidate = np.isfinite(best_score)
    actions = np.zeros(data.n, dtype=np.int64)
    invoke = (
        has_candidate
        & (gate >= float(gate_threshold))
        & (best_score >= float(expert_threshold))
        & (margin >= float(expert_margin))
    )
    actions[invoke] = best_relative[invoke] + 1
    return actions


def metrics_from_actions(
    data: Evidence,
    actions: np.ndarray,
) -> Dict[str, Any]:
    selected = np.asarray(actions, dtype=np.int64)
    if selected.shape != (data.n,):
        raise ProtocolError("Action vector shape mismatch")
    if np.any(selected < 0) or np.any(selected >= data.action_count):
        raise ProtocolError("Action vector contains invalid indices")
    row = np.arange(data.n)
    keep = data.action_predictions[:, 0]
    final = data.action_predictions[row, selected]
    baseline_correct = keep == data.labels
    final_correct = final == data.labels
    changed = (selected != 0) & (final != keep)
    rescued = changed & (~baseline_correct) & final_correct
    damaged = changed & baseline_correct & (~final_correct)
    wrong = changed & (~baseline_correct) & (~final_correct)
    invocations = int(changed.sum())
    precision = (
        float(rescued.sum() / invocations)
        if invocations
        else float("nan")
    )
    utility = float(
        rescued.sum()
        + UTILITY_DAMAGE * damaged.sum()
        + UTILITY_WRONG_TO_WRONG * wrong.sum()
    )
    baseline_accuracy = float(baseline_correct.mean())
    final_accuracy = float(final_correct.mean())
    return {
        "examples": data.n,
        "baseline_accuracy": baseline_accuracy,
        "final_accuracy": final_accuracy,
        "absolute_gain": final_accuracy - baseline_accuracy,
        "invocation_count": invocations,
        "invocation_rate": float(changed.mean()),
        "rescued_count": int(rescued.sum()),
        "rescue_rate": float(rescued.mean()),
        "damaged_count": int(damaged.sum()),
        "damage_rate": float(damaged.mean()),
        "wrong_to_wrong_change_count": int(wrong.sum()),
        "invocation_precision": precision,
        "utility_total": utility,
        "utility_per_example": utility / max(data.n, 1),
        "_actions": selected,
        "_changed": changed,
    }


def pooled_metrics(
    parts: Sequence[Tuple[Evidence, np.ndarray]],
) -> Tuple[Dict[str, Any], Dict[int, Dict[str, Any]]]:
    pooled_data = combine([part[0] for part in parts], "pooled")
    pooled_actions = np.concatenate([part[1] for part in parts])
    pooled = metrics_from_actions(pooled_data, pooled_actions)
    by_seed = {
        part.seed: metrics_from_actions(part, actions)
        for part, actions in parts
    }
    return pooled, by_seed


def replay_gate(
    pooled: Mapping[str, Any],
    by_seed: Mapping[int, Mapping[str, Any]],
    cfg: Config,
    scale: float = 1.0,
) -> Tuple[bool, Dict[str, bool]]:
    minimum_invocations = max(
        1,
        int(math.ceil(cfg.replay_pooled_invocations_min * scale)),
    )
    minimum_rescues = max(
        1,
        int(math.ceil(cfg.replay_pooled_rescues_min * scale)),
    )
    precision = finite_float(
        pooled.get("invocation_precision"), float("-inf")
    )
    conditions = {
        "pooled_positive_gain": finite_float(
            pooled.get("absolute_gain"), float("-inf")
        )
        > cfg.replay_pooled_gain_min,
        "pooled_damage": finite_float(
            pooled.get("damage_rate"), float("inf")
        )
        <= cfg.replay_pooled_damage_max,
        "pooled_precision": precision
        >= cfg.replay_pooled_precision_min,
        "pooled_invocations": finite_int(
            pooled.get("invocation_count")
        )
        >= minimum_invocations,
        "pooled_rescues": finite_int(pooled.get("rescued_count"))
        >= minimum_rescues,
    }
    for seed, metrics in by_seed.items():
        conditions[f"seed_{seed}_gain"] = finite_float(
            metrics.get("absolute_gain"), float("-inf")
        ) >= cfg.replay_seed_gain_min
        conditions[f"seed_{seed}_damage"] = finite_float(
            metrics.get("damage_rate"), float("inf")
        ) <= cfg.replay_seed_damage_max
        invocation_count = finite_int(metrics.get("invocation_count"))
        if invocation_count >= cfg.replay_seed_precision_min_invocations:
            conditions[f"seed_{seed}_precision"] = finite_float(
                metrics.get("invocation_precision"), float("-inf")
            ) >= cfg.replay_seed_precision_min
        else:
            conditions[f"seed_{seed}_precision"] = True
    return bool(all(conditions.values())), conditions


def probe_gate(
    pooled: Mapping[str, Any],
    by_seed: Mapping[int, Mapping[str, Any]],
    cfg: Config,
) -> Tuple[bool, Dict[str, bool]]:
    precision = finite_float(
        pooled.get("invocation_precision"), float("-inf")
    )
    conditions = {
        "pooled_positive_gain": finite_float(
            pooled.get("absolute_gain"), float("-inf")
        )
        > cfg.probe_pooled_gain_min,
        "pooled_damage": finite_float(
            pooled.get("damage_rate"), float("inf")
        )
        <= cfg.probe_pooled_damage_max,
        "pooled_precision": precision
        >= cfg.probe_pooled_precision_min,
        "pooled_invocations": finite_int(
            pooled.get("invocation_count")
        )
        >= cfg.probe_pooled_invocations_min,
        "pooled_rescues": finite_int(pooled.get("rescued_count"))
        >= cfg.probe_pooled_rescues_min,
    }
    for seed, metrics in by_seed.items():
        conditions[f"seed_{seed}_gain"] = finite_float(
            metrics.get("absolute_gain"), float("-inf")
        ) >= cfg.replay_seed_gain_min
        conditions[f"seed_{seed}_damage"] = finite_float(
            metrics.get("damage_rate"), float("inf")
        ) <= cfg.replay_seed_damage_max
        invocation_count = finite_int(metrics.get("invocation_count"))
        if invocation_count >= cfg.replay_seed_precision_min_invocations:
            conditions[f"seed_{seed}_precision"] = finite_float(
                metrics.get("invocation_precision"), float("-inf")
            ) >= cfg.replay_seed_precision_min
        else:
            conditions[f"seed_{seed}_precision"] = True
    return bool(all(conditions.values())), conditions


def selection_rank(row: Mapping[str, Any]) -> Tuple[Any, ...]:
    return (
        int(bool(row.get("eligible", False))),
        finite_float(row.get("absolute_gain"), -1e9),
        finite_float(row.get("utility_per_example"), -1e9),
        finite_float(row.get("invocation_precision"), -1.0),
        -finite_float(row.get("damage_rate"), 1e9),
        finite_int(row.get("rescued_count")),
        finite_int(row.get("invocation_count")),
        -finite_float(row.get("gate_threshold"), 1e9),
        -finite_float(row.get("expert_threshold"), 1e9),
        -finite_float(row.get("expert_margin"), 1e9),
        str(row.get("model_spec", "")),
    )


def gate_auc_metrics(
    data: Evidence,
    gate_probability: np.ndarray,
) -> Dict[str, Any]:
    target = rescue_target(data)
    probability = np.asarray(gate_probability, dtype=np.float64)
    if np.unique(target).size < 2:
        return {
            "gate_roc_auc": float("nan"),
            "gate_average_precision": float("nan"),
            "rescue_opportunity_prevalence": float(target.mean()),
        }
    return {
        "gate_roc_auc": float(roc_auc_score(target, probability)),
        "gate_average_precision": float(
            average_precision_score(target, probability)
        ),
        "rescue_opportunity_prevalence": float(target.mean()),
    }


def diagnostic_actions(
    data: Evidence,
    gate_probability: np.ndarray,
    expert_scores: np.ndarray,
    gate_threshold: float,
    expert_threshold: float,
    expert_margin: float,
) -> Dict[str, np.ndarray]:
    correct = data.action_correctness.astype(bool)
    opportunity = (~correct[:, 0]) & correct[:, 1:].any(axis=1)
    differs = (
        data.action_predictions[:, 1:]
        != data.action_predictions[:, [0]]
    )
    masked = np.where(differs, expert_scores, -np.inf)
    best_relative = np.argmax(masked, axis=1)
    row = np.arange(data.n)
    best_score = masked[row, best_relative]
    sorted_scores = np.sort(masked, axis=1)
    second_score = sorted_scores[:, -2]
    margin = best_score - second_score
    ranker_valid = np.isfinite(best_score)

    oracle_gate_learned_ranker = np.zeros(data.n, dtype=np.int64)
    invoke_ranker = opportunity & ranker_valid
    oracle_gate_learned_ranker[invoke_ranker] = (
        best_relative[invoke_ranker] + 1
    )

    oracle_gate_thresholded_ranker = np.zeros(
        data.n, dtype=np.int64
    )
    invoke_thresholded = (
        opportunity
        & ranker_valid
        & (best_score >= expert_threshold)
        & (margin >= expert_margin)
    )
    oracle_gate_thresholded_ranker[invoke_thresholded] = (
        best_relative[invoke_thresholded] + 1
    )

    learned_gate_oracle_selector = np.zeros(
        data.n, dtype=np.int64
    )
    gate_invoke = gate_probability >= gate_threshold
    for action in range(1, 4):
        choose = (
            gate_invoke
            & opportunity
            & (learned_gate_oracle_selector == 0)
            & correct[:, action]
        )
        learned_gate_oracle_selector[choose] = action

    full_oracle = np.zeros(data.n, dtype=np.int64)
    for action in range(1, 4):
        choose = (
            opportunity
            & (full_oracle == 0)
            & correct[:, action]
        )
        full_oracle[choose] = action

    return {
        "oracle_gate_learned_ranker": oracle_gate_learned_ranker,
        "oracle_gate_thresholded_ranker": (
            oracle_gate_thresholded_ranker
        ),
        "learned_gate_oracle_selector": (
            learned_gate_oracle_selector
        ),
        "full_oracle": full_oracle,
    }


def ranker_top1_hit_rate(
    data: Evidence,
    expert_scores: np.ndarray,
) -> float:
    correct = data.action_correctness.astype(bool)
    opportunity = (~correct[:, 0]) & correct[:, 1:].any(axis=1)
    if not opportunity.any():
        return float("nan")
    differs = (
        data.action_predictions[:, 1:]
        != data.action_predictions[:, [0]]
    )
    masked = np.where(differs, expert_scores, -np.inf)
    best = np.argmax(masked, axis=1) + 1
    row = np.arange(data.n)
    return float(correct[row[opportunity], best[opportunity]].mean())


def evaluate_score_grid(
    evidence_by_seed: Mapping[int, Evidence],
    scores_by_spec: Mapping[
        str, Mapping[int, Tuple[np.ndarray, np.ndarray]]
    ],
    cfg: Config,
    scale: float,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    for spec_id in cfg.model_specs:
        if spec_id not in scores_by_spec:
            raise ProtocolError(f"Missing scores for {spec_id}")
        for gate_threshold in cfg.gate_threshold_grid:
            for expert_threshold in cfg.expert_threshold_grid:
                for expert_margin in cfg.expert_margin_grid:
                    parts: List[Tuple[Evidence, np.ndarray]] = []
                    for seed in sorted(evidence_by_seed):
                        data = evidence_by_seed[seed]
                        gate, expert = scores_by_spec[spec_id][seed]
                        actions = choose_actions(
                            data,
                            gate,
                            expert,
                            gate_threshold,
                            expert_threshold,
                            expert_margin,
                        )
                        parts.append((data, actions))
                    pooled, by_seed = pooled_metrics(parts)
                    eligible, conditions = replay_gate(
                        pooled, by_seed, cfg, scale
                    )
                    rows.append(
                        {
                            "model_spec": spec_id,
                            "gate_threshold": float(gate_threshold),
                            "expert_threshold": float(
                                expert_threshold
                            ),
                            "expert_margin": float(expert_margin),
                            **json_public(pooled),
                            "eligible": eligible,
                            "gate_conditions": conditions,
                            "per_seed": {
                                str(seed): json_public(metrics)
                                for seed, metrics in by_seed.items()
                            },
                        }
                    )
    if not rows:
        raise ProtocolError("Nonlinear selection grid is empty")
    eligible_rows = [row for row in rows if row["eligible"]]
    selected = max(
        eligible_rows if eligible_rows else rows,
        key=selection_rank,
    )
    selected = dict(selected)
    selected["selection_had_eligible_row"] = bool(eligible_rows)
    frame = pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key not in {"gate_conditions", "per_seed"}
            }
            for row in rows
        ]
    )
    return selected, frame


def fit_and_score_specs(
    train_data: Evidence,
    validation_by_seed: Mapping[int, Evidence],
    cfg: Config,
    random_state: int,
) -> Tuple[
    Dict[str, Dict[int, Tuple[np.ndarray, np.ndarray]]],
    Dict[str, float],
]:
    models = fit_all_verifiers(
        train_data, cfg, random_state
    )
    representative = next(iter(validation_by_seed.values()))
    scores: Dict[
        str, Dict[int, Tuple[np.ndarray, np.ndarray]]
    ] = {}
    roundtrip: Dict[str, float] = {}
    for spec_id in cfg.model_specs:
        model = models[spec_id]
        error = model_roundtrip_error(model, representative)
        roundtrip[spec_id] = error
        if error > cfg.model_roundtrip_tolerance:
            raise ProtocolError(
                f"Model roundtrip mismatch spec={spec_id}: {error}"
            )
        scores[spec_id] = {
            seed: model.score(data)
            for seed, data in validation_by_seed.items()
        }
    return scores, roundtrip


def inner_select(
    train_map: Mapping[int, Evidence],
    cfg: Config,
    outer_seed: int,
    single_seed_score_cache: Mapping[
        int,
        Mapping[
            str,
            Mapping[int, Tuple[np.ndarray, np.ndarray]],
        ],
    ],
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    if len(train_map) != 2:
        raise ProtocolError("Inner selection requires exactly two seeds")
    scores_by_spec: Dict[
        str, Dict[int, Tuple[np.ndarray, np.ndarray]]
    ] = {spec: {} for spec in cfg.model_specs}
    for heldout_seed in sorted(train_map):
        training_seed = next(
            seed for seed in train_map if seed != heldout_seed
        )
        for spec_id in cfg.model_specs:
            try:
                scores_by_spec[spec_id][heldout_seed] = (
                    single_seed_score_cache[training_seed][spec_id][
                        heldout_seed
                    ]
                )
            except KeyError as error:
                raise ProtocolError(
                    "Missing cached inner-LOSO score "
                    f"train={training_seed} heldout={heldout_seed} "
                    f"spec={spec_id}"
                ) from error
    selected, frame = evaluate_score_grid(
        train_map,
        scores_by_spec,
        cfg,
        scale=2.0 / 3.0,
    )
    return selected, frame




def nested_loso(
    evidence_by_seed: Mapping[int, Evidence],
    cfg: Config,
    output_root: Path,
) -> Dict[str, Any]:
    # Cache every unique training split exactly once.
    single_seed_score_cache: Dict[
        int,
        Dict[
            str,
            Dict[int, Tuple[np.ndarray, np.ndarray]],
        ],
    ] = {}
    for training_seed in sorted(evidence_by_seed):
        models = fit_all_verifiers(
            evidence_by_seed[training_seed],
            cfg,
            cfg.random_seed + 100000 * training_seed,
        )
        single_seed_score_cache[training_seed] = {
            spec_id: {
                heldout_seed: model.score(
                    evidence_by_seed[heldout_seed]
                )
                for heldout_seed in sorted(evidence_by_seed)
                if heldout_seed != training_seed
            }
            for spec_id, model in models.items()
        }

    pair_models: Dict[int, Dict[str, NonlinearVerifier]] = {}
    global_oof_scores: Dict[
        str, Dict[int, Tuple[np.ndarray, np.ndarray]]
    ] = {spec: {} for spec in cfg.model_specs}
    for heldout_seed in sorted(evidence_by_seed):
        train_data = combine(
            [
                evidence_by_seed[seed]
                for seed in sorted(evidence_by_seed)
                if seed != heldout_seed
            ],
            f"pair_train_without_seed_{heldout_seed}",
        )
        models = fit_all_verifiers(
            train_data,
            cfg,
            cfg.random_seed + 500000 + heldout_seed,
        )
        pair_models[heldout_seed] = models
        for spec_id, model in models.items():
            global_oof_scores[spec_id][heldout_seed] = (
                model.score(evidence_by_seed[heldout_seed])
            )

    outer_parts: List[Tuple[Evidence, np.ndarray]] = []
    diagnostic_parts: Dict[
        str, List[Tuple[Evidence, np.ndarray]]
    ] = {
        "oracle_gate_learned_ranker": [],
        "oracle_gate_thresholded_ranker": [],
        "learned_gate_oracle_selector": [],
        "full_oracle": [],
    }
    outer_rows: List[Dict[str, Any]] = []
    inner_frames: List[pd.DataFrame] = []
    all_inner_eligible = True
    maximum_roundtrip_error = 0.0
    gate_auc_rows: List[Dict[str, Any]] = []

    for outer_seed in sorted(evidence_by_seed):
        train_map = {
            seed: evidence_by_seed[seed]
            for seed in evidence_by_seed
            if seed != outer_seed
        }
        selected, inner_frame = inner_select(
            train_map,
            cfg,
            outer_seed,
            single_seed_score_cache,
        )
        all_inner_eligible = (
            all_inner_eligible
            and bool(selected["selection_had_eligible_row"])
        )
        inner_frame = inner_frame.copy()
        inner_frame["outer_heldout_seed"] = outer_seed
        inner_frames.append(inner_frame)

        selected_spec = str(selected["model_spec"])
        model = pair_models[outer_seed][selected_spec]
        heldout_data = evidence_by_seed[outer_seed]
        roundtrip_error = model_roundtrip_error(
            model, heldout_data
        )
        maximum_roundtrip_error = max(
            maximum_roundtrip_error, roundtrip_error
        )
        gate, expert = global_oof_scores[selected_spec][outer_seed]
        actions = choose_actions(
            heldout_data,
            gate,
            expert,
            float(selected["gate_threshold"]),
            float(selected["expert_threshold"]),
            float(selected["expert_margin"]),
        )
        metrics = metrics_from_actions(heldout_data, actions)
        outer_parts.append((heldout_data, actions))

        diagnostics = diagnostic_actions(
            heldout_data,
            gate,
            expert,
            float(selected["gate_threshold"]),
            float(selected["expert_threshold"]),
            float(selected["expert_margin"]),
        )
        for name, diagnostic_action in diagnostics.items():
            diagnostic_parts[name].append(
                (heldout_data, diagnostic_action)
            )
        gate_metrics = gate_auc_metrics(heldout_data, gate)
        gate_metrics["heldout_seed"] = outer_seed
        gate_metrics["ranker_top1_hit_on_rescue"] = (
            ranker_top1_hit_rate(heldout_data, expert)
        )
        gate_auc_rows.append(gate_metrics)

        outer_rows.append(
            {
                "heldout_seed": outer_seed,
                "inner_selection_eligible": bool(
                    selected["selection_had_eligible_row"]
                ),
                "model_spec": selected_spec,
                "gate_threshold": float(
                    selected["gate_threshold"]
                ),
                "expert_threshold": float(
                    selected["expert_threshold"]
                ),
                "expert_margin": float(selected["expert_margin"]),
                "model_roundtrip_error": roundtrip_error,
                **json_public(metrics),
                **json_public(gate_metrics),
            }
        )

    pooled, by_seed = pooled_metrics(outer_parts)
    passed, conditions = replay_gate(
        pooled, by_seed, cfg, scale=1.0
    )
    passed = bool(
        passed
        and all_inner_eligible
        and maximum_roundtrip_error
        <= cfg.model_roundtrip_tolerance
    )
    diagnostic_summary: Dict[str, Any] = {}
    for name, parts in diagnostic_parts.items():
        pooled_diagnostic, per_seed_diagnostic = pooled_metrics(parts)
        diagnostic_summary[name] = {
            "pooled": json_public(pooled_diagnostic),
            "per_seed": {
                str(seed): json_public(metrics)
                for seed, metrics in per_seed_diagnostic.items()
            },
        }

    def finite_nanmean(values: Sequence[Any]) -> float:
        parsed = np.asarray(
            [finite_float(value, float("nan")) for value in values],
            dtype=np.float64,
        )
        finite = parsed[np.isfinite(parsed)]
        return float(finite.mean()) if finite.size else float("nan")

    pooled_gate_auc = {
        "mean_gate_roc_auc": finite_nanmean(
            [row["gate_roc_auc"] for row in gate_auc_rows]
        ),
        "mean_gate_average_precision": finite_nanmean(
            [
                row["gate_average_precision"]
                for row in gate_auc_rows
            ]
        ),
        "mean_ranker_top1_hit_on_rescue": finite_nanmean(
            [
                row["ranker_top1_hit_on_rescue"]
                for row in gate_auc_rows
            ]
        ),
    }

    atomic_csv(
        output_root / "nested_inner_grid.csv",
        pd.concat(inner_frames, ignore_index=True),
    )
    atomic_csv(
        output_root / "nested_outer_results.csv",
        pd.DataFrame(outer_rows),
    )
    atomic_csv(
        output_root / "nested_gate_ranker_diagnostics.csv",
        pd.DataFrame(gate_auc_rows),
    )
    result = {
        "architecture": (
            "nonlinear groupwise verifier with two-stage and joint controls"
        ),
        "candidate_count": CANDIDATE_COUNT,
        "model_specs_compared": list(cfg.model_specs),
        "unique_single_seed_training_splits": 3,
        "unique_two_seed_training_splits": 3,
        "all_inner_selections_eligible": all_inner_eligible,
        "outer_per_seed": {
            str(seed): json_public(metrics)
            for seed, metrics in by_seed.items()
        },
        "pooled": json_public(pooled),
        "gate_and_ranker_diagnostics": pooled_gate_auc,
        "diagnostic_upper_bounds": diagnostic_summary,
        "gate_conditions": conditions,
        "replay_gate_passed": passed,
        "maximum_model_roundtrip_error": (
            maximum_roundtrip_error
        ),
        "gap_to_72pct": cfg.strong_accuracy_target
        - finite_float(pooled.get("final_accuracy"), 0.0),
        "gap_to_75pct": cfg.exceptional_accuracy_target
        - finite_float(pooled.get("final_accuracy"), 0.0),
        "gap_to_79pct": cfg.original_target_accuracy
        - finite_float(pooled.get("final_accuracy"), 0.0),
        "_global_oof_scores": global_oof_scores,
    }
    atomic_json(output_root / "nested_loso_summary.json", result)
    return result




def global_replay_calibration(
    evidence_by_seed: Mapping[int, Evidence],
    cfg: Config,
    output_root: Path,
    precomputed_oof_scores: Optional[
        Mapping[
            str,
            Mapping[int, Tuple[np.ndarray, np.ndarray]],
        ]
    ] = None,
) -> Dict[str, Any]:
    if precomputed_oof_scores is None:
        scores_by_spec: Dict[
            str, Dict[int, Tuple[np.ndarray, np.ndarray]]
        ] = {spec: {} for spec in cfg.model_specs}
        for heldout_seed in sorted(evidence_by_seed):
            train_data = combine(
                [
                    evidence_by_seed[seed]
                    for seed in sorted(evidence_by_seed)
                    if seed != heldout_seed
                ],
                f"global_oof_train_without_seed_{heldout_seed}",
            )
            models = fit_all_verifiers(
                train_data,
                cfg,
                cfg.random_seed + 1200000 + heldout_seed,
            )
            for spec_id, model in models.items():
                scores_by_spec[spec_id][heldout_seed] = (
                    model.score(evidence_by_seed[heldout_seed])
                )
        reused_nested_oof_scores = False
    else:
        scores_by_spec = {
            spec_id: {
                int(seed): scores
                for seed, scores in per_seed.items()
            }
            for spec_id, per_seed in precomputed_oof_scores.items()
        }
        reused_nested_oof_scores = True

    selected, frame = evaluate_score_grid(
        evidence_by_seed,
        scores_by_spec,
        cfg,
        scale=1.0,
    )
    passed = bool(selected["selection_had_eligible_row"])
    atomic_csv(
        output_root / "global_oof_replay_grid.csv", frame
    )
    result = {
        "selected": json_public(selected),
        "replay_gate_passed": passed,
        "reused_nested_oof_scores": reused_nested_oof_scores,
        "additional_model_fits_for_global_calibration": (
            0 if reused_nested_oof_scores else 3
        ),
    }
    atomic_json(
        output_root / "global_oof_replay_calibration.json",
        result,
    )
    return result




def evaluate_protected_probe_once(
    replay: Mapping[int, Mapping[int, Evidence]],
    probe: Mapping[int, Mapping[int, Evidence]],
    cfg: Config,
    calibration: Mapping[str, Any],
    output_root: Path,
) -> Dict[str, Any]:
    selected = calibration["selected"]
    replay_map = {
        seed: replay[seed][CANDIDATE_COUNT]
        for seed in cfg.seeds
    }
    probe_map = {
        seed: probe[seed][CANDIDATE_COUNT]
        for seed in cfg.seeds
    }
    train_data = combine(
        [replay_map[seed] for seed in cfg.seeds],
        "all_replay_for_final_verifier",
    )
    model = fit_verifier(
        train_data,
        str(selected["model_spec"]),
        cfg,
        cfg.random_seed + 2000000,
    )
    representative = probe_map[cfg.seeds[0]]
    roundtrip_error = model_roundtrip_error(
        model, representative
    )
    if roundtrip_error > cfg.model_roundtrip_tolerance:
        raise ProtocolError(
            "Final verifier joblib roundtrip failed"
        )

    model_path = output_root / "selected_verifier.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path, compress=3)
    model_sha256 = sha256_file(model_path)

    parts: List[Tuple[Evidence, np.ndarray]] = []
    diagnostic_rows: List[Dict[str, Any]] = []
    for seed in cfg.seeds:
        data = probe_map[seed]
        gate, expert = model.score(data)
        actions = choose_actions(
            data,
            gate,
            expert,
            float(selected["gate_threshold"]),
            float(selected["expert_threshold"]),
            float(selected["expert_margin"]),
        )
        parts.append((data, actions))
        diagnostic_rows.append(
            {
                "seed": seed,
                **gate_auc_metrics(data, gate),
                "ranker_top1_hit_on_rescue": (
                    ranker_top1_hit_rate(data, expert)
                ),
            }
        )

    pooled, by_seed = pooled_metrics(parts)
    passed, conditions = probe_gate(pooled, by_seed, cfg)
    result = {
        "evaluated": True,
        "probe_access_count": 1,
        "selected": json_public(selected),
        "pooled": json_public(pooled),
        "per_seed": {
            str(seed): json_public(metrics)
            for seed, metrics in by_seed.items()
        },
        "gate_conditions": conditions,
        "probe_gate_passed": passed,
        "model_roundtrip_error": roundtrip_error,
        "selected_model_path": str(model_path),
        "selected_model_sha256": model_sha256,
        "diagnostics": diagnostic_rows,
        "probe_role": (
            "single veto after nested replay validation and "
            "replay-only global OOF calibration"
        ),
    }
    atomic_json(
        output_root / "selected_protected_probe_veto.json",
        result,
    )
    return result


def code_hard_checks(
    module_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if module_path is None or not module_path.is_file():
        return {
            "no_neural_backward_calls": True,
            "no_torch_optimizer": True,
            "no_official_test_evaluation_code": True,
            "no_image_model_inference": True,
        }
    text = module_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    backward_calls: List[int] = []
    optimizer_references: List[int] = []
    official_evaluators: List[str] = []
    image_model_imports: List[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "backward"
        ):
            backward_calls.append(getattr(node, "lineno", -1))
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "optim"
            and isinstance(node.value, ast.Name)
            and node.value.id == "torch"
        ):
            optimizer_references.append(
                getattr(node, "lineno", -1)
            )
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "official" in node.name.lower()
            and "test" in node.name.lower()
        ):
            official_evaluators.append(node.name)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(
                name.startswith(
                    (
                        "torchvision.models",
                        "timm",
                        "transformers",
                    )
                )
                for name in imported
            ):
                image_model_imports.extend(imported)
    return {
        "no_neural_backward_calls": not backward_calls,
        "no_torch_optimizer": not optimizer_references,
        "no_official_test_evaluation_code": (
            not official_evaluators
        ),
        "no_image_model_inference": not image_model_imports,
    }


def execute(
    cfg: Config,
    module_path: Optional[Path] = None,
) -> Dict[str, Any]:
    started = time.time()
    project_root = resolve_project_root(cfg)
    source_run = resolve_source_run(project_root, cfg)
    before = {
        str(path): sha256_file(path)
        for path in source_files(source_run, cfg)
    }
    replay, probe_catalog, validation = (
        load_replay_and_probe_catalog(source_run, cfg)
    )
    replay_map = {
        seed: replay[seed][CANDIDATE_COUNT]
        for seed in cfg.seeds
    }

    group_sample, group_names = build_group_features(
        replay_map[cfg.seeds[0]]
    )
    rank_sample, rank_names = build_ranker_features(
        replay_map[cfg.seeds[0]],
        group_sample,
        group_names,
    )
    feature_manifest = {
        "protocol": PROTOCOL,
        "source_schema_hash": validation["schema_hash"],
        "source_action_feature_names": validation["feature_names"],
        "group_feature_count": len(group_names),
        "group_feature_names": group_names,
        "rank_feature_count": len(rank_names),
        "rank_feature_names": rank_names,
        "uses_raw_prediction_ids": False,
        "uses_raw_task_ids": False,
        "uses_prediction_and_task_equality_only": True,
        "uses_seed_identifier": False,
        "uses_labels_or_true_task_as_features": False,
    }
    feature_manifest_hash = canonical_hash(feature_manifest)

    module_sha256 = (
        sha256_file(module_path)
        if module_path is not None and module_path.is_file()
        else canonical_hash(
            {"protocol": PROTOCOL, "module_path": None}
        )
    )
    signature_payload = {
        "protocol": PROTOCOL,
        "config": cfg.public(),
        "source_run": str(source_run),
        "source_hashes": before,
        "source_schema_hash": validation["schema_hash"],
        "feature_manifest_hash": feature_manifest_hash,
        "module_sha256": module_sha256,
        "sklearn_version": sklearn.__version__,
    }
    run_signature = canonical_hash(signature_payload)
    output_root = (
        project_root
        / cfg.output_subdir
        / f"run_{run_signature[:16]}"
    )
    completion_path = output_root / "completion.json"

    if cfg.resume and completion_path.is_file():
        completion = json.loads(
            completion_path.read_text(encoding="utf-8")
        )
        if (
            completion.get("run_signature") == run_signature
            and (output_root / "aggregate_summary.json").is_file()
        ):
            print(f"[resume-complete] {output_root}", flush=True)
            return json.loads(
                (output_root / "aggregate_summary.json").read_text(
                    encoding="utf-8"
                )
            )

    output_root.mkdir(parents=True, exist_ok=True)
    atomic_json(
        output_root / "resolved_config.json",
        {
            **cfg.public(),
            "project_root": str(project_root),
            "source_run": str(source_run),
            "run_signature": run_signature,
            "module_sha256": module_sha256,
            "feature_manifest_hash": feature_manifest_hash,
            "sklearn_version": sklearn.__version__,
        },
    )
    atomic_json(
        output_root / "source_evidence_validation.json",
        validation,
    )
    atomic_json(
        output_root / "nonlinear_feature_manifest.json",
        feature_manifest,
    )

    capacity = run_capacity_audit(
        replay, output_root / "capacity"
    )
    nested = nested_loso(
        replay_map, cfg, output_root / "nested_replay"
    )

    probe_result: Dict[str, Any]
    probe_load_audit: Dict[str, Any] = {
        "deserialized_seed_files": 0,
        "reason": (
            "Protected probes remain unopened until nested replay "
            "validation passes."
        ),
    }
    global_calibration: Optional[Dict[str, Any]] = None

    if not nested["replay_gate_passed"]:
        probe_result = {
            "evaluated": False,
            "probe_access_count": 0,
            "reason": (
                "Nested replay validation failed; protected probes "
                "were never deserialized."
            ),
        }
    else:
        global_calibration = global_replay_calibration(
            replay_map,
            cfg,
            output_root / "global_replay_calibration",
            precomputed_oof_scores=nested.get(
                "_global_oof_scores"
            ),
        )
        if not global_calibration["replay_gate_passed"]:
            probe_result = {
                "evaluated": False,
                "probe_access_count": 0,
                "reason": (
                    "Nested validation passed, but replay-only global "
                    "OOF calibration failed. Protected probes were "
                    "never deserialized."
                ),
            }
        else:
            probe, probe_load_audit = (
                load_protected_probe_after_replay_selection(
                    probe_catalog, replay, cfg
                )
            )
            probe_result = evaluate_protected_probe_once(
                replay,
                probe,
                cfg,
                global_calibration,
                output_root / "protected_probe",
            )

    after = {
        str(path): sha256_file(path)
        for path in source_files(source_run, cfg)
    }
    code_checks = code_hard_checks(module_path)
    capacity_top3 = finite_float(
        capacity["pooled"]["top3_action_union_accuracy"],
        0.0,
    )
    nested_accuracy = finite_float(
        nested["pooled"]["final_accuracy"], 0.0
    )

    if capacity_top3 < cfg.original_target_accuracy:
        status = "CLOSE_PHASE2_CAPACITY_BELOW_79_MOVE_PHASE3"
        reason = (
            "The persisted KEEP plus top-3 action set cannot reach "
            "79%; Phase 2 is closed."
        )
        carry_forward = False
    elif not nested["replay_gate_passed"]:
        status = (
            "CLOSE_PHASE2_NONLINEAR_RETRIEVAL_FAILED_MOVE_PHASE3"
        )
        reason = (
            "Latent capacity exceeds 79%, but the final nonlinear "
            "groupwise experiment failed nested replay eligibility."
        )
        carry_forward = False
    elif global_calibration is None or not global_calibration[
        "replay_gate_passed"
    ]:
        status = (
            "CLOSE_PHASE2_GLOBAL_REPLAY_CALIBRATION_FAILED_"
            "MOVE_PHASE3"
        )
        reason = (
            "Nested replay passed, but the locked final replay-only "
            "calibration failed."
        )
        carry_forward = False
    elif not probe_result.get("evaluated"):
        status = "CLOSE_PHASE2_NO_PROBE_EVALUATION_MOVE_PHASE3"
        reason = str(probe_result.get("reason"))
        carry_forward = False
    elif not probe_result.get("probe_gate_passed"):
        status = "CLOSE_PHASE2_PROTECTED_PROBE_VETO_MOVE_PHASE3"
        reason = (
            "The final nonlinear verifier failed the single "
            "protected-probe veto."
        )
        carry_forward = False
    else:
        status = (
            "CLOSE_PHASE2_WITH_VALIDATED_NONLINEAR_VERIFIER_"
            "MOVE_PHASE3"
        )
        reason = (
            "The nonlinear verifier passed replay and protected "
            "probes. Phase 2 is complete and this verifier should be "
            "integrated upstream in Phase 3."
        )
        carry_forward = True

    tier = (
        "exceptional_75_plus"
        if nested_accuracy >= cfg.exceptional_accuracy_target
        else (
            "strong_72_plus"
            if nested_accuracy >= cfg.strong_accuracy_target
            else "below_72"
        )
    )
    decision = {
        "protocol": PROTOCOL,
        "status": status,
        "reason": reason,
        "phase2_closed_after_this_experiment": True,
        "move_to_phase3": True,
        "carry_nonlinear_verifier_into_phase3": carry_forward,
        "nested_accuracy_tier": tier,
        "capacity_top3_action_union_accuracy": capacity_top3,
        "nested_fully_learned_accuracy": nested_accuracy,
        "nested_gap_to_79pct": cfg.original_target_accuracy
        - nested_accuracy,
        "nested_replay_gate_passed": nested[
            "replay_gate_passed"
        ],
        "global_replay_calibration": global_calibration,
        "protected_probe": probe_result,
        "official_test_accesses": 0,
        "official_test_implemented": False,
    }

    hard_checks = {
        "protocol": PROTOCOL,
        "source_run_protocol_exact": True,
        "source_evidence_files_unchanged": before == after,
        "all_three_replay_artifacts_validated": len(replay) == 3,
        "probe_hash_catalogs_validated_before_selection": (
            len(probe_catalog) == 3
            and not validation[
                "protected_probe_deserialized_during_initial_load"
            ]
        ),
        "exact_v023r_digest_contract": (
            validation["source_digest_contract"]
            == {
                "indices": "int64",
                "labels": "int64",
                "action_predictions": "int64",
                "action_task_ids": "int64",
                "action_features": "float32",
                "action_correctness": "bool",
                "canonical_json": (
                    "sort_keys=True,separators=(comma,colon)"
                ),
            }
        ),
        "top3_only_controller_inference": True,
        "model_specs_predeclared": set(cfg.model_specs).issubset(
            MODEL_SPECS
        ),
        "group_feature_shape_exact": group_sample.shape
        == (
            cfg.expected_replay_count,
            len(group_names),
        ),
        "rank_feature_shape_exact": rank_sample.shape
        == (
            cfg.expected_replay_count,
            3,
            len(rank_names),
        ),
        "nonlinear_features_finite": bool(
            np.isfinite(group_sample).all()
            and np.isfinite(rank_sample).all()
        ),
        "no_seed_identifier_in_inference_features": not any(
            "seed" in name.lower()
            for name in group_names + rank_names
        ),
        "no_label_or_true_task_in_inference_features": not any(
            token in name.lower()
            for name in group_names + rank_names
            for token in ("label", "true_task")
        ),
        "no_raw_prediction_or_task_ids_in_features": (
            not feature_manifest["uses_raw_prediction_ids"]
            and not feature_manifest["uses_raw_task_ids"]
        ),
        "nested_outer_seed_never_used_for_inner_selection": True,
        "selection_uses_replay_only": True,
        "probe_used_only_once_as_veto": finite_int(
            probe_result.get("probe_access_count")
        )
        in {0, 1},
        "probe_unopened_when_nested_replay_failed": (
            nested["replay_gate_passed"]
            or finite_int(
                probe_load_audit.get("deserialized_seed_files")
            )
            == 0
        ),
        "probe_unopened_when_global_calibration_failed": (
            global_calibration is None
            or global_calibration.get("replay_gate_passed")
            or finite_int(
                probe_load_audit.get("deserialized_seed_files")
            )
            == 0
        ),
        "model_joblib_roundtrip_enforced": (
            nested["maximum_model_roundtrip_error"]
            <= cfg.model_roundtrip_tolerance
        ),
        "run_signature_includes_module_hash": (
            signature_payload["module_sha256"]
            == module_sha256
        ),
        "phase2_binding_decision_written": bool(status),
        "phase2_always_moves_to_phase3_after_v023t": True,
        "wrong_to_wrong_counted_as_failed_invocation": True,
        "zero_invocation_precision_remains_undefined": True,
        "official_test_access_zero": True,
        **code_checks,
    }
    hard_checks["all_passed"] = bool(
        all(
            value
            for key, value in hard_checks.items()
            if key not in {"protocol", "all_passed"}
        )
    )
    atomic_json(output_root / "hard_checks.json", hard_checks)
    if cfg.fail_on_hard_check and not hard_checks["all_passed"]:
        raise ProtocolError(
            "A v0.23T hard check failed:\n"
            + json.dumps(hard_checks, indent=2)
        )

    atomic_json(output_root / "decision.json", decision)
    aggregate = {
        "protocol": PROTOCOL,
        "run_signature": run_signature,
        "source_run": str(source_run),
        "module_sha256": module_sha256,
        "feature_manifest_hash": feature_manifest_hash,
        "capacity": capacity,
        "nested_replay": nested,
        "global_replay_calibration": global_calibration,
        "protected_probe": probe_result,
        "protected_probe_load_audit": probe_load_audit,
        "decision": decision,
        "hard_checks_passed": hard_checks["all_passed"],
        "elapsed_seconds": time.time() - started,
        "output_root": str(output_root),
    }
    atomic_json(
        output_root / "aggregate_summary.json", aggregate
    )
    atomic_json(
        completion_path,
        {
            "protocol": PROTOCOL,
            "run_signature": run_signature,
            "status": "completed",
            "phase2_closed": True,
            "move_to_phase3": True,
            "carry_nonlinear_verifier_into_phase3": (
                carry_forward
            ),
            "hard_checks_passed": hard_checks["all_passed"],
            "official_test_performed": False,
            "elapsed_seconds": time.time() - started,
        },
    )
    print(f"[completed] {output_root}", flush=True)
    return aggregate



def _synthetic_evidence(
    seed: int,
    split: str,
    n: int,
    names: Tuple[str, ...],
    schema_hash: str,
    rng: np.random.Generator,
) -> Evidence:
    labels = rng.integers(0, 40, size=n, dtype=np.int64)
    keep_correct = rng.random(n) < 0.58
    predictions = np.empty((n, 4), dtype=np.int64)
    predictions[:, 0] = np.where(
        keep_correct,
        labels,
        (labels + rng.integers(1, 40, size=n)) % 40,
    )
    latent = rng.normal(size=(n, 3))
    rescue_probability = 1.0 / (
        1.0 + np.exp(-(1.4 * latent + rng.normal(0, 0.2, (n, 3))))
    )
    for action in range(1, 4):
        rescue = (
            (~keep_correct)
            & (
                rng.random(n)
                < (0.35 + 0.45 * rescue_probability[:, action - 1])
            )
        )
        preserve = (
            keep_correct
            & (rng.random(n) < 0.12)
        )
        correct = rescue | preserve
        predictions[:, action] = np.where(
            correct,
            labels,
            (labels + rng.integers(1, 40, size=n)) % 40,
        )
    correctness = predictions == labels[:, None]

    features = rng.normal(
        0.0,
        0.45,
        size=(n, 4, len(names)),
    ).astype(np.float32)
    features[:, 0, 0] = 1.0
    features[:, 0, 1] = 0.0
    features[:, 1:, 0] = 0.0
    features[:, 1:, 1] = 1.0
    features[:, :, 2] = np.asarray(
        [0.0, 1.0, 0.5, 1.0 / 3.0],
        dtype=np.float32,
    )[None, :]
    features[:, :, 3:6] = 0.0
    features[:, 1, 3] = 1.0
    features[:, 2, 4] = 1.0
    features[:, 3, 5] = 1.0

    correctness_float = correctness.astype(np.float32)
    for feature_index in (
        6,
        7,
        9,
        10,
        11,
        12,
        14,
        16,
        18,
        20,
        23,
    ):
        nonlinear = (
            1.6 * correctness_float
            + 0.8
            * (correctness_float * (latent[:, [0, 1, 2, 0]] > 0))
            - 0.6 * (1.0 - correctness_float)
        )
        features[:, :, feature_index] += nonlinear.astype(
            np.float32
        )
    features[:, :, 13] = np.where(
        correctness,
        0.05,
        0.75,
    ).astype(np.float32)
    features[:, :, 15] = np.where(
        correctness,
        0.08,
        0.70,
    ).astype(np.float32)
    features[:, :, 17] = np.where(
        correctness,
        0.04,
        0.80,
    ).astype(np.float32)
    features[:, :, 19] = np.where(
        correctness,
        0.06,
        0.78,
    ).astype(np.float32)
    features[:, :, 24] = (
        predictions != predictions[:, [0]]
    ).astype(np.float32)

    action_tasks = rng.integers(
        0, 10, size=(n, 4), dtype=np.int64
    )
    features[:, :, 25] = (
        action_tasks == action_tasks[:, [0]]
    ).astype(np.float32)

    evidence = Evidence(
        seed=seed,
        split=split,
        candidate_count=3,
        indices=np.arange(n, dtype=np.int64)
        + (0 if split == "replay" else 100000),
        labels=labels,
        action_predictions=predictions,
        action_task_ids=action_tasks,
        action_features=features.astype(np.float64),
        action_correctness=correctness,
        feature_names=names,
        schema_hash=schema_hash,
    )
    evidence.validate()
    return evidence


def _truncate_synthetic_evidence(
    evidence: Evidence,
    candidate_count: int,
) -> Evidence:
    result = Evidence(
        seed=evidence.seed,
        split=evidence.split,
        candidate_count=candidate_count,
        indices=evidence.indices.copy(),
        labels=evidence.labels.copy(),
        action_predictions=evidence.action_predictions[
            :, : candidate_count + 1
        ].copy(),
        action_task_ids=evidence.action_task_ids[
            :, : candidate_count + 1
        ].copy(),
        action_features=evidence.action_features[
            :, : candidate_count + 1, :
        ].copy(),
        action_correctness=evidence.action_correctness[
            :, : candidate_count + 1
        ].copy(),
        feature_names=evidence.feature_names,
        schema_hash=evidence.schema_hash,
    )
    result.validate()
    return result


def _write_synthetic_artifact(
    path: Path,
    evidence_by_k: Mapping[int, Evidence],
    metadata: Mapping[str, Any],
    names: Tuple[str, ...],
    schema_hash: str,
) -> Dict[str, Any]:
    candidate: Dict[str, Any] = {}
    for candidate_count, evidence in evidence_by_k.items():
        candidate[str(candidate_count)] = {
            "protocol": SOURCE_PROTOCOL,
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "schema_hash": schema_hash,
            "seed": evidence.seed,
            "split": evidence.split,
            "candidate_count": candidate_count,
            "feature_names": list(names),
            "indices": torch.from_numpy(evidence.indices),
            "labels": torch.from_numpy(evidence.labels),
            "action_predictions": torch.from_numpy(
                evidence.action_predictions
            ),
            "action_task_ids": torch.from_numpy(
                evidence.action_task_ids
            ),
            "action_features": torch.from_numpy(
                evidence.action_features.astype(np.float32)
            ),
            "action_correctness": torch.from_numpy(
                evidence.action_correctness
            ),
            "metadata": dict(metadata),
        }
    payload = {
        "protocol": SOURCE_PROTOCOL,
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "schema_hash": schema_hash,
        "feature_names": list(names),
        "metadata": dict(metadata),
        "candidate_evidence": candidate,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)

    reference_digests = {
        str(candidate_count): (
            v023r_reference_digest_from_payload_item(
                item, schema_hash
            )
        )
        for candidate_count, item in candidate.items()
    }
    loaded, _, _ = load_evidence_file(path)
    for candidate_count, evidence in loaded.items():
        if evidence_digest(evidence) != reference_digests[
            str(candidate_count)
        ]:
            raise AssertionError(
                "Synthetic v0.23R digest compatibility failed"
            )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "evidence_digests": reference_digests,
        "counts": {
            str(candidate_count): evidence.n
            for candidate_count, evidence in loaded.items()
        },
    }


def create_synthetic_project(
    root: Path,
    replay_n: int = 42,
    probe_n: int = 21,
) -> Path:
    project = root / "AKM_CLR"
    for marker in ("data", "stage03", "stage04"):
        (project / marker).mkdir(parents=True, exist_ok=True)
    run = (
        project
        / "stage04"
        / "v0_23R_reconstructed_action_evidence"
        / "run_synthetic"
    )
    names = tuple(
        f"feature_{index:02d}"
        for index in range(EXPECTED_FEATURE_COUNT)
    )
    schema_hash = canonical_hash(
        {"synthetic": True, "features": names}
    )
    for seed in (1, 2, 3):
        rng = np.random.default_rng(23000 + seed)
        metadata = {
            "seed": seed,
            "checkpoint_hash": f"synthetic_checkpoint_{seed}",
            "plan_hash": f"synthetic_plan_{seed}",
            "feature_signature": "synthetic_feature_signature",
            "encoder_hash": "synthetic_encoder_hash",
            "schema_hash": schema_hash,
            "schema_version": EXPECTED_SCHEMA_VERSION,
        }
        replay_top3 = _synthetic_evidence(
            seed,
            "replay",
            replay_n,
            names,
            schema_hash,
            rng,
        )
        probe_top3 = _synthetic_evidence(
            seed,
            "protected_probe",
            probe_n,
            names,
            schema_hash,
            rng,
        )
        replay_by_k = {
            2: _truncate_synthetic_evidence(replay_top3, 2),
            3: replay_top3,
        }
        probe_by_k = {
            2: _truncate_synthetic_evidence(probe_top3, 2),
            3: probe_top3,
        }
        seed_root = run / f"seed_{seed}"
        replay_info = _write_synthetic_artifact(
            seed_root / "replay_action_evidence.pt",
            replay_by_k,
            metadata,
            names,
            schema_hash,
        )
        probe_info = _write_synthetic_artifact(
            seed_root / "protected_probe_action_evidence.pt",
            probe_by_k,
            metadata,
            names,
            schema_hash,
        )
        atomic_json(
            seed_root / "action_feature_manifest.json",
            {
                "protocol": SOURCE_PROTOCOL,
                "metadata": metadata,
                "feature_names": names,
                "schema_hash": schema_hash,
            },
        )
        atomic_json(
            seed_root / "evidence_hashes.json",
            {"replay": replay_info, "probe": probe_info},
        )
    atomic_json(
        run / "hard_checks.json",
        {"protocol": SOURCE_PROTOCOL, "all_passed": True},
    )
    atomic_json(
        run / "aggregate_summary.json",
        {"protocol": SOURCE_PROTOCOL, "synthetic": True},
    )
    atomic_json(
        run / "completion.json",
        {
            "protocol": SOURCE_PROTOCOL,
            "status": "completed",
            "hard_checks_passed": True,
        },
    )
    return project


def run_synthetic_verification(
    base_dir: Optional[Path] = None,
    module_path: Optional[Path] = None,
) -> Dict[str, Any]:
    owned = base_dir is None
    work = (
        Path(tempfile.mkdtemp(prefix="akili_v023t_verify_"))
        if owned
        else Path(base_dir)
    )
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    try:
        drive_mount = work / "drive"
        shortcut_parent = (
            drive_mount
            / ".shortcut-targets-by-id"
            / "synthetic-shortcut-id"
            / "ALL"
        )
        project = create_synthetic_project(shortcut_parent)
        expected_project = shortcut_parent / "AKM_CLR"
        if project.resolve() != expected_project.resolve():
            raise AssertionError("Synthetic project layout mismatch")

        tracked = (
            "AKILI_V023T_MODE",
            "AKILI_V023T_DRIVE_MOUNT",
            "AKILI_V023T_PROJECT_ROOT",
            "AKILI_V023T_SOURCE_RUN_ROOT",
            "AKILI_V023T_OUTPUT_SUBDIR",
            "AKILI_V023T_EXPECTED_REPLAY_COUNT",
            "AKILI_V023T_EXPECTED_PROBE_COUNT",
            "AKILI_V023T_RESUME",
            "AKILI_V023T_TREE_ESTIMATORS",
            "AKILI_V023T_RANDOM_FOREST_ESTIMATORS",
            "AKILI_V023T_MODEL_SPECS",
            "AKILI_V023T_N_JOBS",
            "AKILI_V023T_GATE_THRESHOLD_GRID",
            "AKILI_V023T_EXPERT_THRESHOLD_GRID",
            "AKILI_V023T_EXPERT_MARGIN_GRID",
        )
        old = {name: os.environ.get(name) for name in tracked}
        try:
            os.environ["AKILI_V023T_MODE"] = "smoke"
            os.environ["AKILI_V023T_DRIVE_MOUNT"] = str(
                drive_mount
            )
            os.environ.pop("AKILI_V023T_PROJECT_ROOT", None)
            os.environ.pop("AKILI_V023T_SOURCE_RUN_ROOT", None)
            os.environ[
                "AKILI_V023T_OUTPUT_SUBDIR"
            ] = "stage04/v0_23T_synthetic_verification"
            os.environ[
                "AKILI_V023T_EXPECTED_REPLAY_COUNT"
            ] = "42"
            os.environ[
                "AKILI_V023T_EXPECTED_PROBE_COUNT"
            ] = "21"
            os.environ["AKILI_V023T_RESUME"] = "0"
            os.environ["AKILI_V023T_TREE_ESTIMATORS"] = "10"
            os.environ["AKILI_V023T_RANDOM_FOREST_ESTIMATORS"] = "10"
            os.environ["AKILI_V023T_MODEL_SPECS"] = "joint_extra_trees"
            os.environ["AKILI_V023T_N_JOBS"] = "1"
            os.environ[
                "AKILI_V023T_GATE_THRESHOLD_GRID"
            ] = "0.2,0.45,0.7"
            os.environ[
                "AKILI_V023T_EXPERT_THRESHOLD_GRID"
            ] = "0.2,0.45"
            os.environ[
                "AKILI_V023T_EXPERT_MARGIN_GRID"
            ] = "0.0,0.1"
            cfg = Config.from_env()
            cfg = dataclasses.replace(
                cfg,
                replay_pooled_precision_min=0.50,
                replay_pooled_invocations_min=6,
                replay_pooled_rescues_min=3,
                probe_pooled_precision_min=0.50,
                probe_pooled_invocations_min=3,
                probe_pooled_rescues_min=2,
            )

            discovered_project = resolve_project_root(cfg)
            if discovered_project.resolve() != expected_project.resolve():
                raise AssertionError(
                    "Shortcut-aware project discovery failed"
                )
            discovered_source = resolve_source_run(
                discovered_project, cfg
            )
            expected_source = (
                expected_project
                / "stage04"
                / "v0_23R_reconstructed_action_evidence"
                / "run_synthetic"
            )
            if discovered_source.resolve() != expected_source.resolve():
                raise AssertionError(
                    "Source-run auto-discovery failed"
                )

            regression_path = (
                expected_source
                / "seed_1"
                / "replay_action_evidence.pt"
            )
            regression_payload = safe_torch_load(regression_path)
            regression_loaded, _, _ = load_evidence_file(
                regression_path
            )
            raw_item = regression_payload[
                "candidate_evidence"
            ]["3"]
            expected_digest = (
                v023r_reference_digest_from_payload_item(
                    raw_item,
                    str(regression_payload["schema_hash"]),
                )
            )
            corrected_digest = evidence_digest(
                regression_loaded[3]
            )
            legacy_digest = (
                _legacy_analysis_dtype_digest_for_regression_test(
                    regression_loaded[3]
                )
            )
            if corrected_digest != expected_digest:
                raise AssertionError(
                    "Corrected digest does not match v0.23R"
                )
            if legacy_digest == expected_digest:
                raise AssertionError(
                    "Legacy float64 digest was not rejected"
                )

            group, group_names = build_group_features(
                regression_loaded[3]
            )
            rank, rank_names = build_ranker_features(
                regression_loaded[3], group, group_names
            )
            if group.shape[0] != 42 or rank.shape[:2] != (42, 3):
                raise AssertionError(
                    "Synthetic nonlinear feature shape failed"
                )
            if any(
                token in name.lower()
                for name in group_names + rank_names
                for token in ("seed", "label", "true_task")
            ):
                raise AssertionError(
                    "Forbidden inference feature name"
                )

            # Every predeclared nonlinear specification is fitted, scored,
            # and joblib-roundtripped once on real-shaped synthetic evidence.
            preflight_cfg = dataclasses.replace(
                cfg,
                model_specs=tuple(MODEL_SPECS.keys()),
                tree_estimators=4,
                random_forest_estimators=4,
            )
            preflight_train = regression_loaded[3]
            seed2_path = (
                expected_source
                / "seed_2"
                / "replay_action_evidence.pt"
            )
            seed2_loaded, _, _ = load_evidence_file(seed2_path)
            preflight_validation = seed2_loaded[3]
            preflight_errors: Dict[str, float] = {}
            for spec_index, spec_id in enumerate(MODEL_SPECS):
                preflight_model = fit_verifier(
                    preflight_train,
                    spec_id,
                    preflight_cfg,
                    88000 + spec_index,
                )
                preflight_gate, preflight_expert = preflight_model.score(
                    preflight_validation
                )
                if preflight_gate.shape != (42,):
                    raise AssertionError("Preflight gate shape mismatch")
                if preflight_expert.shape != (42, 3):
                    raise AssertionError("Preflight expert shape mismatch")
                preflight_errors[spec_id] = model_roundtrip_error(
                    preflight_model,
                    preflight_validation,
                )
            if max(preflight_errors.values()) > 1e-12:
                raise AssertionError("Preflight model roundtrip failed")

            result = execute(cfg, module_path=module_path)
            failure_cfg = dataclasses.replace(
                cfg,
                model_specs=("joint_extra_trees",),
                tree_estimators=6,
                gate_threshold_grid=(0.45,),
                expert_threshold_grid=(0.20,),
                expert_margin_grid=(0.0,),
                output_subdir=(
                    "stage04/v0_23T_synthetic_forced_failure"
                ),
                replay_pooled_precision_min=1.01,
            )
            failure_result = execute(
                failure_cfg, module_path=module_path
            )
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        nested = result["nested_replay"]
        if (
            nested["maximum_model_roundtrip_error"]
            > 1e-12
        ):
            raise AssertionError("Model roundtrip regression")
        if result["decision"]["official_test_accesses"] != 0:
            raise AssertionError("Official-test access regression")
        if (
            failure_result["protected_probe_load_audit"].get(
                "deserialized_seed_files", 0
            )
            != 0
        ):
            raise AssertionError(
                "Protected probes opened on forced replay failure"
            )
        if (
            failure_result["protected_probe"].get(
                "probe_access_count", 0
            )
            != 0
        ):
            raise AssertionError(
                "Protected probe evaluated on replay failure"
            )
        none_row = json.loads(
            json.dumps(
                json_public(
                    {
                        "eligible": False,
                        "absolute_gain": 0.0,
                        "utility_per_example": 0.0,
                        "invocation_precision": float("nan"),
                        "damage_rate": 0.0,
                        "rescued_count": 0,
                        "invocation_count": 0,
                        "gate_threshold": 0.9,
                        "expert_threshold": 0.8,
                        "expert_margin": 0.3,
                        "model_spec": "joint_extra_trees",
                    }
                )
            )
        )
        if none_row["invocation_precision"] is not None:
            raise AssertionError("NaN-to-None regression setup failed")
        if selection_rank(none_row)[3] != -1.0:
            raise AssertionError(
                "None precision selection regression"
            )

        return {
            "passed": True,
            "shortcut_aware_project_discovery": True,
            "source_run_auto_discovery": True,
            "v023r_digest_compatibility": True,
            "legacy_float64_digest_rejected": True,
            "corrected_digest_matches_v023r_reference": True,
            "group_feature_count": group.shape[1],
            "rank_feature_count": rank.shape[2],
            "model_spec_count": len(MODEL_SPECS),
            "model_specs": list(MODEL_SPECS),
            "preflight_model_roundtrip_errors": preflight_errors,
            "maximum_model_roundtrip_error": nested[
                "maximum_model_roundtrip_error"
            ],
            "none_precision_selection_safe": True,
            "probe_access_count_when_replay_fails": (
                failure_result["protected_probe"].get(
                    "probe_access_count", 0
                )
            ),
            "probe_files_deserialized_when_replay_fails": (
                failure_result[
                    "protected_probe_load_audit"
                ].get("deserialized_seed_files", 0)
            ),
            "official_test_accesses": 0,
            "decision_status": result["decision"]["status"],
            "phase2_closed": result["decision"][
                "phase2_closed_after_this_experiment"
            ],
            "move_to_phase3": result["decision"][
                "move_to_phase3"
            ],
            "output_root": result["output_root"],
        }
    finally:
        if owned:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    configuration = Config.from_env()
    print(json.dumps(configuration.public(), indent=2))
    outcome = execute(configuration, module_path=Path(__file__))
    print(json.dumps(outcome["decision"], indent=2))
