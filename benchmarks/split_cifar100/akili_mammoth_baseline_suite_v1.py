
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

PROTOCOL = "akili-mammoth-baseline-suite-v1"
OFFICIAL_REPOSITORY = "https://github.com/aimagelab/mammoth.git"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    environment: Optional[Mapping[str, str]] = None,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if environment:
        env.update({key: str(value) for key, value in environment.items()})
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return int(process.returncode)


def git_commit(repo: Path) -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    return process.stdout.strip() if process.returncode == 0 else "unknown"


def validate_mammoth(repo: Path) -> None:
    required = [repo / "main.py", repo / "models", repo / "datasets", repo / "utils"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Invalid Mammoth repository: {missing}")


def discover_mammoth(project_root: Path, explicit: str = "") -> Path:
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.extend([
        project_root / "Mammoth",
        project_root / "mammoth",
        project_root / "third_party" / "mammoth",
        Path("/content/mammoth"),
    ])
    for candidate in candidates:
        if (candidate / "main.py").is_file():
            validate_mammoth(candidate)
            return candidate.resolve()
    raise FileNotFoundError(
        "Mammoth was not found. Set AKILI_MAMMOTH_ROOT to the existing Drive checkout. "
        "The runner does not clone by default."
    )


def cifar_integrity_root(candidate: Path) -> Optional[Path]:
    candidate = candidate.expanduser().resolve()
    possible = [candidate, candidate / "CIFAR100"]
    for root in possible:
        folder = root / "cifar-100-python"
        if all((folder / name).is_file() for name in ("train", "test", "meta")):
            return root.parent if root.name == "CIFAR100" else root
    return None


def discover_cifar_base(project_root: Path, explicit: str = "") -> Path:
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend([
        project_root / "data",
        project_root / "datasets",
        project_root,
        Path("/content/drive/MyDrive/AKM_CLR/data"),
    ])
    for candidate in candidates:
        if not candidate.exists():
            continue
        integrity = cifar_integrity_root(candidate)
        if integrity is not None:
            return integrity
        for folder in candidate.rglob("cifar-100-python"):
            if all((folder / name).is_file() for name in ("train", "test", "meta")):
                if folder.parent.name == "CIFAR100":
                    return folder.parent.parent.resolve()
    raise FileNotFoundError(
        "A complete CIFAR-100 cache was not found. This runner refuses to download it. "
        "Set AKILI_DERPP_DATA_ROOT to the directory containing CIFAR100/cifar-100-python."
    )


def help_flags(repo: Path, model: str, dataset: str) -> Set[str]:
    process = subprocess.run(
        [sys.executable, "main.py", "--model", model, "--dataset", dataset, "--help"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    text = process.stdout + "\n" + process.stderr
    return set(re.findall(r"--[A-Za-z0-9_-]+", text))


def add_if_supported(
    command: List[str],
    flags: Set[str],
    name: str,
    value: Optional[Any] = None,
) -> None:
    if name not in flags:
        return
    command.append(name)
    if value is not None:
        command.append(str(value))


def snapshot_files(repo: Path) -> Dict[str, Tuple[int, int]]:
    roots = [repo / "results", repo / "logs", repo / "checkpoints"]
    state: Dict[str, Tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                stat = path.stat()
                state[str(path.resolve())] = (stat.st_size, stat.st_mtime_ns)
    return state


def copy_changed_files(
    repo: Path,
    before: Mapping[str, Tuple[int, int]],
    destination: Path,
) -> List[str]:
    after = snapshot_files(repo)
    changed = [Path(path) for path, sig in after.items() if before.get(path) != sig]
    copied: List[str] = []
    for source in changed:
        relative = None
        for root_name in ("results", "logs", "checkpoints"):
            root = repo / root_name
            try:
                relative = Path(root_name) / source.relative_to(root.resolve())
                break
            except ValueError:
                continue
        if relative is None:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())
    return copied


def extract_console_metrics(log_path: Path) -> Dict[str, Any]:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = [
        line.strip()
        for line in text.splitlines()
        if any(token in line.lower() for token in (
            "class-il", "task-il", "accuracy", "forgetting", "backward"
        ))
    ]
    return {"matching_lines": lines[-100:]}


def build_command(
    repo: Path,
    *,
    model: str,
    dataset: str,
    seed: int,
    base_path: Path,
    buffer_size: int,
    minibatch_size: int,
    mode: str,
) -> Tuple[List[str], Set[str]]:
    flags = help_flags(repo, model, dataset)
    command = [sys.executable, "main.py", "--model", model, "--dataset", dataset]
    add_if_supported(command, flags, "--seed", seed)
    add_if_supported(command, flags, "--base_path", str(base_path))
    add_if_supported(command, flags, "--num_workers", 0)
    add_if_supported(command, flags, "--permute_classes", 0)
    add_if_supported(command, flags, "--savecheck", "last")
    add_if_supported(command, flags, "--csv_log", 1)
    if mode == "smoke":
        add_if_supported(command, flags, "--debug_mode", 1)
    else:
        add_if_supported(command, flags, "--model_config", "best")
    if model in {"er", "der", "derpp", "er_ace"}:
        add_if_supported(command, flags, "--buffer_size", buffer_size)
        add_if_supported(command, flags, "--minibatch_size", minibatch_size)
    return command, flags


def run_suite(
    *,
    repo: Path,
    base_path: Path,
    output_root: Path,
    models: Sequence[str],
    seeds: Sequence[int],
    buffer_size: int,
    minibatch_size: int,
    mode: str,
    force: bool = False,
) -> Dict[str, Any]:
    validate_mammoth(repo)
    output_root.mkdir(parents=True, exist_ok=True)
    commit = git_commit(repo)
    records: List[Dict[str, Any]] = []

    for model in models:
        for seed in seeds:
            run_root = output_root / model / f"seed_{seed}"
            run_root.mkdir(parents=True, exist_ok=True)
            complete_path = run_root / "COMPLETE.json"
            if complete_path.is_file() and not force:
                record = json.loads(complete_path.read_text(encoding="utf-8"))
                if record.get("returncode") == 0:
                    print(f"[resume] {model} seed={seed}")
                    records.append(record)
                    continue

            command, flags = build_command(
                repo,
                model=model,
                dataset="seq-cifar100",
                seed=seed,
                base_path=base_path,
                buffer_size=buffer_size,
                minibatch_size=minibatch_size,
                mode=mode,
            )
            before = snapshot_files(repo)
            log_path = run_root / "console.log"
            print("[run]", " ".join(command))
            returncode = run_command(
                command,
                cwd=repo,
                log_path=log_path,
                environment={"WANDB_MODE": "disabled", "PYTHONHASHSEED": str(seed)},
            )
            copied = copy_changed_files(repo, before, run_root / "mammoth_artifacts")
            metrics = extract_console_metrics(log_path)
            record = {
                "protocol": PROTOCOL,
                "model": model,
                "dataset": "seq-cifar100",
                "seed": seed,
                "mode": mode,
                "buffer_size": buffer_size if model in {"er", "der", "derpp", "er_ace"} else None,
                "minibatch_size": minibatch_size if model in {"er", "der", "derpp", "er_ace"} else None,
                "mammoth_commit": commit,
                "command": command,
                "supported_flags": sorted(flags),
                "returncode": returncode,
                "copied_artifacts": copied,
                "console_metrics": metrics,
                "completed_at": utc_now(),
            }
            complete_path.write_text(
                json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
            )
            records.append(record)
            if returncode != 0:
                raise RuntimeError(
                    f"{model} seed {seed} failed. Read {log_path}. "
                    "Completed runs remain resumable."
                )

    summary = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "mammoth_repository": str(repo),
        "mammoth_commit": commit,
        "cifar_base_path": str(base_path),
        "models": list(models),
        "seeds": list(seeds),
        "mode": mode,
        "records": records,
        "all_completed": all(record["returncode"] == 0 for record in records),
        "important_limit": (
            "This suite measures official Mammoth baselines only. "
            "It is not yet the Akili-vs-DER++ matched ablation."
        ),
    }
    (output_root / "BASELINE_SUITE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    with (output_root / "BASELINE_SUITE_SUMMARY.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model", "seed", "mode", "buffer_size",
                "minibatch_size", "mammoth_commit", "returncode",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in writer.fieldnames})
    return summary


def synthetic_verification(root: Path) -> Dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    repo = root / "mammoth"
    (repo / "models").mkdir(parents=True)
    (repo / "datasets").mkdir()
    (repo / "utils").mkdir()
    fake_main = (
        "import sys\n"
        "if '--help' in sys.argv:\n"
        "    print('--seed --base_path --num_workers --permute_classes --savecheck "
        "--csv_log --debug_mode --model_config --buffer_size --minibatch_size')\n"
        "    raise SystemExit(0)\n"
        "print('Class-IL accuracy: 12.34')\n"
    )
    (repo / "main.py").write_text(fake_main, encoding="utf-8")
    data = root / "data" / "CIFAR100" / "cifar-100-python"
    data.mkdir(parents=True)
    for name in ("train", "test", "meta"):
        (data / name).write_text("x", encoding="utf-8")
    base = discover_cifar_base(root, str(root / "data"))
    command, flags = build_command(
        repo,
        model="derpp",
        dataset="seq-cifar100",
        seed=1,
        base_path=base,
        buffer_size=400,
        minibatch_size=32,
        mode="smoke",
    )
    checks = {
        "repo_valid": True,
        "cache_detected_without_download": base == (root / "data").resolve(),
        "seed_in_command": "--seed" in command,
        "base_path_in_command": "--base_path" in command,
        "buffer_in_command": "--buffer_size" in command,
        "debug_mode_in_smoke": "--debug_mode" in command,
    }
    return {"passed": all(checks.values()), "checks": checks, "command": command}
