#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/create_github_repo.sh <repo-name> [visibility]
# Example:
#   bash scripts/create_github_repo.sh TheEyeBetaDataAPI public

REPO_NAME="${1:-TheEyeBetaDataAPI}"
VISIBILITY="${2:-private}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required."
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login"
  exit 1
fi

if [ ! -d .git ]; then
  git init
  git add .
  git commit -m "Initial commit: TheEyeBetaDataAPI with TypeScript frontend and plugin package"
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin already exists: $(git remote get-url origin)"
else
  gh repo create "${REPO_NAME}" --source=. --remote=origin --"${VISIBILITY}" --push
fi

echo "Repository is ready: $(git remote get-url origin)"
