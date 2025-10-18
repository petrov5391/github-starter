#!/usr/bin/env bash
set -euo pipefail

# Publish this repository to GitHub.
# - If $GITHUB_TOKEN is set with scope "repo", the script will create the
#   repository (if missing) under the authenticated user and then push.
# - Otherwise, it will just attempt to push.

ensure_origin() {
  if ! git remote get-url origin >/dev/null 2>&1; then
    echo "origin is not set. Run ./set-origin.sh first." >&2
    exit 1
  fi
}

parse_origin() {
  local origin
  origin=$(git remote get-url origin)
  if [[ "$origin" =~ ^git@github.com:([^/]+)/([^\.]+)(\.git)?$ ]]; then
    GH_OWNER="${BASH_REMATCH[1]}"
    GH_REPO="${BASH_REMATCH[2]}"
  elif [[ "$origin" =~ ^https://github.com/([^/]+)/([^\.]+)(\.git)?$ ]]; then
    GH_OWNER="${BASH_REMATCH[1]}"
    GH_REPO="${BASH_REMATCH[2]}"
  else
    echo "Unsupported origin URL: $origin" >&2
    exit 1
  fi
}

maybe_create_repo() {
  if [ -z "${GITHUB_TOKEN-}" ]; then
    echo "GITHUB_TOKEN not set — skipping repo creation (will try push)."
    return 0
  fi
  echo "Ensuring repo exists on GitHub: ${GH_OWNER}/${GH_REPO}"
  # Try to fetch repo; if 404, create it.
  status=$(curl -fsS -o /dev/null -w '%{http_code}' \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GH_OWNER}/${GH_REPO}" || true)
  if [ "$status" = "200" ]; then
    echo "Repo already exists."
    return 0
  fi
  echo "Creating repository ${GH_REPO} under the authenticated user..."
  payload="{\"name\":\"${GH_REPO}\",\"private\":true}"
  if [ -n "${GITHUB_REPO_DESCRIPTION-}" ]; then
    # Простейшая вставка описания (без экранирования сложных символов)
    payload="{\"name\":\"${GH_REPO}\",\"private\":true,\"description\":\"${GITHUB_REPO_DESCRIPTION}\"}"
  fi
  create_status=$(curl -fsS -o /dev/null -w '%{http_code}' \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -X POST https://api.github.com/user/repos \
    -d "$payload" || true)
  if [ "$create_status" != "201" ] && [ "$create_status" != "422" ]; then
    echo "Failed to create repo (HTTP $create_status)." >&2
    exit 1
  fi
  echo "Repo ensured on GitHub (status $create_status)."
}

push_repo() {
  export GIT_SSH_COMMAND=${GIT_SSH_COMMAND-"ssh -o StrictHostKeyChecking=accept-new"}
  local branch
  branch=$(git rev-parse --abbrev-ref HEAD)
  if [ -z "$branch" ] || [ "$branch" = "HEAD" ]; then
    echo "Не удалось определить текущую ветку (detached HEAD?). Укажите ветку вручную." >&2
    exit 1
  fi
  echo "Пушу ветку: $branch"
  git push -u origin "$branch"
}

main() {
  cd "$(dirname "$0")"
  ensure_origin
  parse_origin
  maybe_create_repo
  push_repo
}

main "$@"
