from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .store import AkiliStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="akili", description="Akili Runtime public alpha")
    parser.add_argument("--db", default=".akili/akili.db", help="SQLite store path")
    parser.add_argument("--version", action="version", version=f"akili-runtime {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialise the local Akili store")
    remember = sub.add_parser("remember", help="Activate a scoped procedural memory")
    remember.add_argument("--scope", required=True)
    remember.add_argument("--family", required=True)
    remember.add_argument("--content", required=True)
    remember.add_argument("--source", required=True)
    run = sub.add_parser("run", help="Build an auditable context bundle for an agent task")
    run.add_argument("--scope", required=True)
    run.add_argument("--task", required=True)
    run.add_argument("--family", action="append", dest="families")
    audit = sub.add_parser("audit", help="Print audit entries and chain validity")
    audit.add_argument("--scope")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = AkiliStore(args.db)
    if args.command == "init":
        print(json.dumps({"store": str(Path(args.db)), "audit_valid": store.validate_audit_chain()}, indent=2))
    elif args.command == "remember":
        print(json.dumps(store.remember(scope=args.scope, family=args.family, content=args.content, source=args.source).to_dict(), indent=2, ensure_ascii=False))
    elif args.command == "run":
        print(json.dumps(store.context_bundle(scope=args.scope, task=args.task, families=args.families), indent=2, ensure_ascii=False))
    elif args.command == "audit":
        print(json.dumps({"valid": store.validate_audit_chain(), "entries": store.audit_entries(scope=args.scope)}, indent=2, ensure_ascii=False))
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
