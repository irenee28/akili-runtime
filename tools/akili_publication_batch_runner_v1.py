
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


PROTOCOL = "akili-publication-notebook-batch-runner-v1"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def hard_checks_status(run_root: Optional[Path]) -> Optional[bool]:
    if run_root is None:
        return None
    path = run_root / "hard_checks.json"
    payload = read_json(path) if path.is_file() else None
    if payload is None:
        return None
    if isinstance(payload.get("all_passed"), bool):
        return bool(payload["all_passed"])
    bool_values = [value for value in payload.values() if isinstance(value, bool)]
    return all(bool_values) if bool_values else None


def newest_run(output_root: Path) -> Optional[Path]:
    runs = sorted(
        (path for path in output_root.glob("run_*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return runs[0] if runs else None


def execute_notebook(
    source_notebook: Path,
    executed_notebook: Path,
    *,
    environment: Mapping[str, str],
    log_path: Path,
    timeout_seconds: int = 0,
) -> int:
    executed_notebook.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(source_notebook),
        "--output",
        str(executed_notebook),
        "--ExecutePreprocessor.kernel_name=python3",
        f"--ExecutePreprocessor.timeout={timeout_seconds}",
    ]
    env = dict(os.environ)
    env.update({key: str(value) for key, value in environment.items()})
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return int(process.returncode)


def evidence_zip(batch_root: Path, destination: Path) -> None:
    excluded_suffixes = {".safetensors", ".pt", ".pth", ".bin", ".ckpt"}
    excluded_parts = {"checkpoints", "__pycache__", ".ipynb_checkpoints"}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in batch_root.rglob("*") if item.is_file()):
            if path.suffix.lower() in excluded_suffixes:
                continue
            if any(part in excluded_parts for part in path.parts):
                continue
            archive.write(path, path.relative_to(batch_root).as_posix())


def run_seed_batch(
    *,
    source_notebook: Path,
    batch_root: Path,
    seeds: Sequence[int],
    env_builder,
    output_root_builder,
    force: bool = False,
) -> Dict[str, Any]:
    batch_root.mkdir(parents=True, exist_ok=True)
    records: List[Dict[str, Any]] = []

    for seed in seeds:
        seed_root = batch_root / f"seed_{seed}"
        seed_root.mkdir(parents=True, exist_ok=True)
        completion_path = seed_root / "COMPLETE.json"
        existing = read_json(completion_path)
        if (
            not force
            and existing is not None
            and existing.get("returncode") == 0
            and existing.get("run_root")
            and Path(str(existing["run_root"])).is_dir()
        ):
            records.append(existing)
            print(f"[resume] seed={seed} already complete")
            continue

        output_root = output_root_builder(seed)
        output_root.mkdir(parents=True, exist_ok=True)
        executed_notebook = seed_root / f"executed_seed_{seed}.ipynb"
        log_path = seed_root / f"seed_{seed}.log"
        environment = env_builder(seed, output_root)
        print(f"[run] seed={seed} output={output_root}")
        returncode = execute_notebook(
            source_notebook,
            executed_notebook,
            environment=environment,
            log_path=log_path,
            timeout_seconds=0,
        )
        run_root = newest_run(output_root)
        all_passed = hard_checks_status(run_root)
        record = {
            "protocol": PROTOCOL,
            "seed": seed,
            "started_output_root": str(output_root),
            "run_root": str(run_root) if run_root else None,
            "returncode": returncode,
            "all_passed": all_passed,
            "executed_notebook": str(executed_notebook),
            "log": str(log_path),
            "completed_at": utc_now(),
        }
        completion_path.write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
        )
        records.append(record)
        if returncode != 0:
            raise RuntimeError(
                f"Seed {seed} failed. Read {log_path}; completed seeds remain resumable."
            )

    aggregate = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "seeds": list(seeds),
        "records": records,
        "all_processes_completed": all(record["returncode"] == 0 for record in records),
        "all_hard_checks_passed": all(record["all_passed"] is True for record in records),
    }
    with (batch_root / "BATCH_SUMMARY.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["seed", "returncode", "all_passed", "run_root", "log"],
        )
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in writer.fieldnames})

    zip_path = batch_root.parent / f"{batch_root.name}_evidence.zip"
    evidence_zip(batch_root, zip_path)
    aggregate["evidence_zip"] = str(zip_path)
    (batch_root / "BATCH_SUMMARY.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8"
    )
    return aggregate


def synthetic_verification(root: Path) -> Dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    fake_run = root / "runs" / "run_test"
    fake_run.mkdir(parents=True, exist_ok=True)
    (fake_run / "hard_checks.json").write_text(
        '{"all_passed": true}', encoding="utf-8"
    )
    checks = {
        "newest_run_detected": newest_run(root / "runs") == fake_run,
        "hard_checks_read": hard_checks_status(fake_run) is True,
    }
    return {"passed": all(checks.values()), "checks": checks}
