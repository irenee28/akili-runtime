#!/usr/bin/env bash
set -Eeuo pipefail

AUTHOR_NAME="${AUTHOR_NAME:-Irénée Akilimali}"
AUTHOR_EMAIL="${AUTHOR_EMAIL:-shukranimungu@gmail.com}"
GITHUB_USER="${GITHUB_USER:-irenee28}"
REPO_NAME="${REPO_NAME:-akili-runtime}"
RELEASE_TAG="${RELEASE_TAG:-v0.1.0-alpha}"
CREATE_RELEASE="${CREATE_RELEASE:-1}"
VALIDATE_ONLY="${VALIDATE_ONLY:-0}"
VENV_DIR="${AKILI_PUBLISH_VENV:-$HOME/.akili-publish-venv}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

required=(
  README.md
  LICENSE
  NOTICE
  pyproject.toml
  docs/RESULTS.md
  docs/CLAIMS_AND_LIMITATIONS.md
)
for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "Missing required file: $file"
done

command -v git >/dev/null 2>&1 || fail "git is required. Install Apple Command Line Tools with: xcode-select --install"

if command -v python3.12 >/dev/null 2>&1; then
  HOST_PYTHON="$(command -v python3.12)"
elif command -v python3.13 >/dev/null 2>&1; then
  HOST_PYTHON="$(command -v python3.13)"
elif command -v python3 >/dev/null 2>&1; then
  HOST_PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  HOST_PYTHON="$(command -v python)"
else
  fail "Python 3.10+ is required. With Homebrew: brew install python@3.12"
fi

"$HOST_PYTHON" - <<'PY' || fail "Python 3.10+ is required. With Homebrew: brew install python@3.12"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

printf 'Using host Python: %s\n' "$HOST_PYTHON"
printf 'Using external validation environment: %s\n' "$VENV_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$HOST_PYTHON" -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_BIN="$VENV_DIR/bin"

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -e '.[dev]' --no-build-isolation
"$VENV_PYTHON" -m pytest

rm -rf .akili
PATH="$VENV_BIN:$PATH" bash examples/quickstart.sh >/tmp/akili_quickstart.log
"$VENV_PYTHON" - <<'PY'
from pathlib import Path
from akili_runtime import AkiliStore

path = Path('.akili/akili.db')
assert path.exists(), 'quickstart did not create the store'
assert AkiliStore(path).validate_audit_chain(), 'audit chain invalid after quickstart'
print('LOCAL RELEASE CHECKS PASS')
PY

rm -rf .akili .pytest_cache build dist
find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
find . -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
find . -type f -name '.DS_Store' -delete

"$VENV_PYTHON" - <<'PY'
from pathlib import Path
import hashlib

root = Path('.')
lines = []
for path in sorted(root.rglob('*')):
    if not path.is_file():
        continue
    if path.name == 'SHA256SUMS' or '.git' in path.parts:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.as_posix()}")
Path('SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY

"$VENV_PYTHON" - <<'PY'
from pathlib import Path
import hashlib

for line in Path('SHA256SUMS').read_text(encoding='utf-8').splitlines():
    expected, relative = line.split('  ', 1)
    actual = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
    assert actual == expected, relative
print('SHA256SUMS VERIFIED')
PY

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  echo "LOCAL VALIDATION COMPLETE; GitHub publication skipped because VALIDATE_ONLY=1."
  exit 0
fi

command -v gh >/dev/null 2>&1 || fail "GitHub CLI is required. With Homebrew: brew install gh"
if ! gh auth status >/dev/null 2>&1; then
  fail "GitHub CLI is not authenticated. Run: gh auth login"
fi
gh auth setup-git >/dev/null 2>&1 || true

if [[ ! -d .git ]]; then
  git init
fi
git branch -M main
git config user.name "$AUTHOR_NAME"
git config user.email "$AUTHOR_EMAIL"

git add .
if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "Initial public Akili Runtime release"
fi

REPO_SLUG="${GITHUB_USER}/${REPO_NAME}"
HTTPS_REMOTE="https://github.com/${REPO_SLUG}.git"
SSH_REMOTE="git@github.com:${REPO_SLUG}.git"

if gh repo view "$REPO_SLUG" >/dev/null 2>&1; then
  if git remote get-url origin >/dev/null 2>&1; then
    current="$(git remote get-url origin)"
    [[ "$current" == "$HTTPS_REMOTE" || "$current" == "$SSH_REMOTE" ]] || \
      fail "Refusing to replace unexpected origin: $current"
  else
    git remote add origin "$HTTPS_REMOTE"
  fi
  git push -u origin main
else
  if git remote get-url origin >/dev/null 2>&1; then
    current="$(git remote get-url origin)"
    [[ "$current" == "$HTTPS_REMOTE" || "$current" == "$SSH_REMOTE" ]] || \
      fail "Unexpected origin exists before repository creation: $current"
    git remote remove origin
  fi
  gh repo create "$REPO_SLUG" \
    --public \
    --description "Scoped, versioned and auditable procedural memory for AI agents" \
    --source . \
    --remote origin \
    --push
fi

if [[ "$CREATE_RELEASE" == "1" ]]; then
  if gh release view "$RELEASE_TAG" --repo "$REPO_SLUG" >/dev/null 2>&1; then
    echo "Release $RELEASE_TAG already exists; skipping."
  else
    assets=(evidence/release-assets/*)
    [[ -e "${assets[0]}" ]] || fail "No files found in evidence/release-assets"
    gh release create "$RELEASE_TAG" "${assets[@]}" \
      --repo "$REPO_SLUG" \
      --title "Akili Runtime v0.1 public alpha" \
      --notes-file docs/RELEASE_NOTES_v0.1.md
  fi
fi

cat <<MSG
PUBLICATION COMPLETE
Repository: https://github.com/${REPO_SLUG}
Release:    https://github.com/${REPO_SLUG}/releases/tag/${RELEASE_TAG}
MSG
