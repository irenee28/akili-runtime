from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("PLACEHOLDER_", "github.com/OWNER/")
SECRET_PATTERNS = (
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
ALLOWED_PLACEHOLDER_FILES = {"README.md", "CITATION.cff", "GITHUB_SETUP.md", "release_audit.py"}


def main() -> int:
    failures = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"possible secret: {path.relative_to(ROOT)}")
        if path.name not in ALLOWED_PLACEHOLDER_FILES:
            for placeholder in PLACEHOLDERS:
                if placeholder in text:
                    failures.append(f"unexpected placeholder in {path.relative_to(ROOT)}: {placeholder}")
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                failures.append(f"invalid JSON {path.relative_to(ROOT)}: {error}")
        if path.suffix == ".ipynb":
            try:
                notebook = json.loads(text)
                for index, cell in enumerate(notebook.get("cells", [])):
                    for output in cell.get("outputs", []):
                        if output.get("output_type") == "error":
                            failures.append(f"notebook error output: {path.relative_to(ROOT)} cell {index}")
            except Exception as error:
                failures.append(f"invalid notebook {path.relative_to(ROOT)}: {error}")
    if failures:
        print("RELEASE AUDIT FAILED")
        for failure in failures:
            print("-", failure)
        return 1
    print("RELEASE AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
