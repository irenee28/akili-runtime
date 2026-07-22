from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List

REQUIRED_ANY = {"summary.json", "hard_checks.json", "registry.json", "audit_chain.jsonl"}
TOKEN_PATTERNS = [
    re.compile(rb"hf_[A-Za-z0-9]{20,}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def scan_tokens(path: Path) -> List[str]:
    if path.stat().st_size > 10 * 1024 * 1024:
        return []
    data = path.read_bytes()
    return [pattern.pattern.decode("ascii", errors="ignore") for pattern in TOKEN_PATTERNS if pattern.search(data)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--maximum-file-mb", type=float, default=50.0)
    args = parser.parse_args()

    args.destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="akili-import-") as temp:
        temp_root = Path(temp)
        if args.source.is_dir():
            source_root = args.source
        elif zipfile.is_zipfile(args.source):
            with zipfile.ZipFile(args.source) as archive:
                archive.extractall(temp_root)
            source_root = temp_root
        else:
            raise FileNotFoundError(f"Source is not a directory or zip: {args.source}")

        source_files = list(iter_files(source_root))
        present_names = {path.name for path in source_files}
        if not (present_names & REQUIRED_ANY):
            raise RuntimeError("No recognized Akili result artifacts found")

        manifest = []
        for source in sorted(source_files):
            relative = source.relative_to(source_root)
            if source.stat().st_size > args.maximum_file_mb * 1024 * 1024:
                continue
            token_hits = scan_tokens(source)
            if token_hits:
                raise RuntimeError(f"Possible secret in {relative}: {token_hits}")
            target = args.destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest.append({
                "path": relative.as_posix(),
                "bytes": source.stat().st_size,
                "sha256": sha256_file(source),
            })

    (args.destination / "IMPORT_MANIFEST.json").write_text(
        json.dumps({"files": manifest}, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({"destination": str(args.destination), "files": len(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
