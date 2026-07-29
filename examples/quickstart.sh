#!/usr/bin/env bash
set -Eeuo pipefail
rm -rf .akili
akili init
akili remember --scope repo:demo --family timestamps --content "Use timezone-aware UTC timestamps" --source issue-42
akili remember --scope repo:demo --family timestamps --content "Use RFC 3339 UTC timestamps ending in Z" --source review-57
akili run --scope repo:demo --task "Add an export timestamp"
akili audit --scope repo:demo
