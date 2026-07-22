
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROTOCOL = "akili-drive-evidence-collector-v1"

SAFE_EXTENSIONS = {
    ".json", ".jsonl", ".csv", ".md", ".txt", ".html", ".htm",
    ".gif", ".mp4", ".webm", ".png", ".jpg", ".jpeg", ".webp",
    ".yaml", ".yml", ".toml", ".ipynb", ".log",
}
WEIGHT_EXTENSIONS = {".safetensors", ".pt", ".pth", ".bin", ".ckpt", ".onnx"}
EXCLUDED_DIR_NAMES = {
    ".git", "__pycache__", ".ipynb_checkpoints", "wandb", "cache",
    "huggingface", "datasets_cache",
}
SECRET_PATTERNS = {
    "huggingface_token": re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    "openai_key": re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
}
RUN_HINTS = ("run_", "seed_", "publication", "result", "output")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def bool_from_hard_checks(path: Path) -> Optional[bool]:
    payload = read_json(path)
    if payload is None:
        return None
    if isinstance(payload.get("all_passed"), bool):
        return bool(payload["all_passed"])
    bools = [value for value in payload.values() if isinstance(value, bool)]
    return all(bools) if bools else None


def family_from_path(path: Path) -> str:
    text = path.as_posix().lower()
    if "agent_evolution" in text:
        return "agent_evolution"
    if "robot" in text or "mujoco" in text or "arm_" in text:
        return "robotics_mujoco"
    if "skill_runtime" in text or "llm" in text:
        return "llm_skill_runtime"
    if "cifar" in text or "phase2" in text or "v0_23" in text:
        return "cifar100"
    if "derpp" in text or "mammoth" in text:
        return "mammoth_baselines"
    return "other"


def find_run_roots(project_root: Path) -> List[Path]:
    candidates: set[Path] = set()
    for path in project_root.rglob("*"):
        if not path.is_dir():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        try:
            child_names = {child.name for child in path.iterdir() if child.is_file()}
        except OSError:
            continue
        has_evidence = bool(
            child_names
            & {
                "summary.json", "hard_checks.json", "registry.json",
                "audit_chain.jsonl", "audit_log.json",
                "FINALIZATION_COMPLETE.json",
                "akili_robotics_v0_2_report.json",
            }
        )
        hinted = any(hint in path.name.lower() for hint in RUN_HINTS)
        if has_evidence or (hinted and any(path.glob("*.json"))):
            candidates.add(path.resolve())

    ordered = sorted(candidates, key=lambda p: len(p.parts), reverse=True)
    selected: List[Path] = []
    for candidate in ordered:
        if not any(candidate in existing.parents for existing in selected):
            selected.append(candidate)
    return sorted(selected)


def detect_summary(run_root: Path) -> Optional[Path]:
    preferred = [
        run_root / "summary.json",
        run_root / "FINALIZATION_COMPLETE.json",
        run_root / "akili_robotics_v0_2_report.json",
    ]
    for path in preferred:
        if path.is_file():
            return path
    reports = sorted(run_root.glob("*report*.json"))
    return reports[0] if reports else None


def detect_hard_checks(run_root: Path) -> Optional[Path]:
    direct = run_root / "hard_checks.json"
    if direct.is_file():
        return direct
    matches = sorted(run_root.rglob("hard_checks.json"))
    return matches[0] if matches else None


def evidence_flags(run_root: Path) -> Dict[str, bool]:
    files = [path for path in run_root.rglob("*") if path.is_file()]
    names = {path.name for path in files}
    suffixes = {path.suffix.lower() for path in files}
    return {
        "has_summary": detect_summary(run_root) is not None,
        "has_hard_checks": detect_hard_checks(run_root) is not None,
        "has_registry": "registry.json" in names,
        "has_audit": bool({"audit_chain.jsonl", "audit_log.json", "audit_chain.json"} & names),
        "has_config": bool(
            {"resolved_config.json", "config.json", "environment.json", "environment_versions.json"} & names
        ),
        "has_media": bool(suffixes & {".gif", ".mp4", ".webm", ".png"}),
        "has_csv": ".csv" in suffixes,
        "has_json_results": any(
            path.suffix.lower() == ".json"
            and any(token in path.name.lower() for token in ("result", "report", "summary", "metric"))
            for path in files
        ),
        "has_weights": bool(suffixes & WEIGHT_EXTENSIONS),
    }


@dataclass
class RunRecord:
    run_root: str
    relative_path: str
    family: str
    modified_utc: str
    total_files: int
    total_bytes: int
    all_passed: Optional[bool]
    status: str
    flags: Dict[str, bool]
    summary_path: Optional[str]
    hard_checks_path: Optional[str]
    missing_for_publication: List[str]

    def public(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def inspect_run(project_root: Path, run_root: Path) -> RunRecord:
    files = [path for path in run_root.rglob("*") if path.is_file()]
    flags = evidence_flags(run_root)
    hard_path = detect_hard_checks(run_root)
    summary_path = detect_summary(run_root)
    all_passed = bool_from_hard_checks(hard_path) if hard_path else None

    missing = []
    for key, label in (
        ("has_summary", "summary/report"),
        ("has_hard_checks", "hard_checks.json"),
        ("has_config", "resolved configuration/environment"),
    ):
        if not flags[key]:
            missing.append(label)
    if flags["has_registry"] and not flags["has_audit"]:
        missing.append("audit chain/log")

    if all_passed is True and not missing:
        status = "publication_candidate"
    elif flags["has_summary"] or flags["has_hard_checks"] or flags["has_json_results"]:
        status = "development_evidence"
    else:
        status = "unfinished_or_unknown"

    return RunRecord(
        run_root=str(run_root),
        relative_path=run_root.relative_to(project_root).as_posix(),
        family=family_from_path(run_root),
        modified_utc=dt.datetime.fromtimestamp(
            run_root.stat().st_mtime, tz=dt.timezone.utc
        ).isoformat(),
        total_files=len(files),
        total_bytes=sum(path.stat().st_size for path in files),
        all_passed=all_passed,
        status=status,
        flags=flags,
        summary_path=str(summary_path) if summary_path else None,
        hard_checks_path=str(hard_path) if hard_path else None,
        missing_for_publication=missing,
    )


def scan_secret(path: Path, maximum_scan_bytes: int = 10 * 1024 * 1024) -> List[str]:
    if path.stat().st_size > maximum_scan_bytes:
        return []
    try:
        data = path.read_bytes()
    except OSError:
        return ["unreadable"]
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(data)]


def should_export(
    path: Path,
    *,
    include_weights: bool,
    maximum_file_bytes: int,
) -> Tuple[bool, str]:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return False, "excluded_directory"
    if path.stat().st_size > maximum_file_bytes:
        return False, "file_too_large"
    suffix = path.suffix.lower()
    if suffix in WEIGHT_EXTENSIONS and not include_weights:
        return False, "weight_excluded"
    name_lower = path.name.lower()
    if any(token in name_lower for token in ("token", "secret", "credential", "apikey", "api_key")):
        return False, "sensitive_filename"
    if suffix not in SAFE_EXTENSIONS and not (include_weights and suffix in WEIGHT_EXTENSIONS):
        return False, "extension_not_public"
    hits = scan_secret(path)
    if hits:
        return False, "possible_secret:" + ",".join(hits)
    return True, "included"


def export_runs(
    project_root: Path,
    records: Sequence[RunRecord],
    output_root: Path,
    *,
    include_weights: bool,
    maximum_file_mb: float,
) -> Dict[str, Any]:
    staging = output_root / "github_ready"
    if staging.exists():
        shutil.rmtree(staging)
    publication_root = staging / "results" / "publication_import"
    development_root = staging / "results" / "development_import"
    publication_root.mkdir(parents=True, exist_ok=True)
    development_root.mkdir(parents=True, exist_ok=True)

    maximum_file_bytes = int(maximum_file_mb * 1024 * 1024)
    manifest: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for record in records:
        source_root = Path(record.run_root)
        destination_base = (
            publication_root if record.status == "publication_candidate"
            else development_root
        ) / record.family / source_root.name
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            allowed, reason = should_export(
                source,
                include_weights=include_weights,
                maximum_file_bytes=maximum_file_bytes,
            )
            relative_inside_run = source.relative_to(source_root)
            if not allowed:
                excluded.append({
                    "run": record.relative_path,
                    "path": relative_inside_run.as_posix(),
                    "reason": reason,
                    "bytes": source.stat().st_size,
                })
                continue
            target = destination_base / relative_inside_run
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest.append({
                "run": record.relative_path,
                "source_relative": source.relative_to(project_root).as_posix(),
                "export_relative": target.relative_to(staging).as_posix(),
                "bytes": source.stat().st_size,
                "sha256": sha256_file(source),
                "status": record.status,
            })

        status_path = destination_base / "PUBLICATION_STATUS.json"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            json.dumps(record.public(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    inventory = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "project_root": str(project_root),
        "include_weights": include_weights,
        "maximum_file_mb": maximum_file_mb,
        "runs": [record.public() for record in records],
        "included_files": manifest,
        "excluded_files": excluded,
    }
    (staging / "DRIVE_INVENTORY.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
    )

    with (staging / "DRIVE_INVENTORY.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "relative_path", "family", "modified_utc", "total_files", "total_bytes",
            "all_passed", "status", "missing_for_publication",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({
                "relative_path": record.relative_path,
                "family": record.family,
                "modified_utc": record.modified_utc,
                "total_files": record.total_files,
                "total_bytes": record.total_bytes,
                "all_passed": record.all_passed,
                "status": record.status,
                "missing_for_publication": "; ".join(record.missing_for_publication),
            })

    lines = [
        "# Akili Drive evidence inventory",
        "",
        f"Generated: {inventory['created_at']}",
        "",
        "| Status | Family | Run | all_passed | Missing |",
        "|---|---|---|---:|---|",
    ]
    for record in records:
        lines.append(
            f"| {record.status} | {record.family} | `{record.relative_path}` | "
            f"{record.all_passed} | {', '.join(record.missing_for_publication) or '—'} |"
        )
    (staging / "PUBLICATION_CANDIDATES.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    checksums = []
    for path in sorted(p for p in staging.rglob("*") if p.is_file()):
        checksums.append(f"{sha256_file(path)}  {path.relative_to(staging).as_posix()}")
    (staging / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    output_root.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / (
        "akili_github_evidence_"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".zip"
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in staging.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(staging).as_posix())

    return {
        "protocol": PROTOCOL,
        "project_root": str(project_root),
        "output_root": str(output_root),
        "zip_path": str(zip_path),
        "staging_root": str(staging),
        "runs_found": len(records),
        "publication_candidates": sum(
            record.status == "publication_candidate" for record in records
        ),
        "development_evidence": sum(
            record.status == "development_evidence" for record in records
        ),
        "included_files": len(manifest),
        "excluded_files": len(excluded),
    }


def collect(
    project_root: Path,
    output_root: Path,
    *,
    include_weights: bool = False,
    maximum_file_mb: float = 75.0,
) -> Dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(project_root)
    run_roots = find_run_roots(project_root)
    records = [inspect_run(project_root, run_root) for run_root in run_roots]
    return export_runs(
        project_root,
        records,
        output_root.expanduser().resolve(),
        include_weights=include_weights,
        maximum_file_mb=maximum_file_mb,
    )


def synthetic_verification(root: Path) -> Dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    project = root / "AKM_CLR"
    good = project / "stage05" / "akili_robotics_v0_2_mujoco" / "run_good"
    partial = project / "stage05" / "akili_skill_runtime_v0_1" / "run_partial"
    good.mkdir(parents=True)
    partial.mkdir(parents=True)

    (good / "summary.json").write_text('{"score": 1.0}', encoding="utf-8")
    (good / "hard_checks.json").write_text('{"all_passed": true}', encoding="utf-8")
    (good / "resolved_config.json").write_text('{"seed": 1}', encoding="utf-8")
    (good / "registry.json").write_text('{"skills": {}}', encoding="utf-8")
    (good / "audit_log.json").write_text('[]', encoding="utf-8")
    (good / "demo.gif").write_bytes(b"GIF89a")
    (good / "adapter_model.safetensors").write_bytes(b"weight")

    (partial / "summary.json").write_text('{"score": 0.5}', encoding="utf-8")
    (partial / "hard_checks.json").write_text('{"all_passed": false}', encoding="utf-8")
    (partial / "resolved_config.json").write_text('{"seed": 1}', encoding="utf-8")

    result = collect(project, root / "exports", include_weights=False, maximum_file_mb=5)
    with zipfile.ZipFile(result["zip_path"]) as archive:
        names = set(archive.namelist())
    checks = {
        "two_runs_found": result["runs_found"] == 2,
        "one_publication_candidate": result["publication_candidates"] == 1,
        "one_development_run": result["development_evidence"] == 1,
        "weights_excluded": not any(name.endswith(".safetensors") for name in names),
        "gif_included": any(name.endswith("demo.gif") for name in names),
        "inventory_written": "DRIVE_INVENTORY.json" in names,
        "checksums_written": "SHA256SUMS" in names,
    }
    return {"passed": all(checks.values()), "checks": checks, "result": result}
