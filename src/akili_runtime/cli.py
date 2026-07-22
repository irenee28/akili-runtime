from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .audit import HashChainAuditLog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="akili")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-audit", help="Verify an Akili JSONL audit chain")
    verify.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify-audit":
        log = HashChainAuditLog(args.path)
        print(json.dumps({"valid": True, "entries": len(log.entries), "head": log.head}, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
