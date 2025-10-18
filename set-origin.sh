#!/usr/bin/env bash
set -euo pipefail

# Использование:
#   ./set-origin.sh <github_user> <repo_name>
#   или без аргументов — интерактивный ввод.

if [ ${#@} -ge 2 ]; then
  GH_USER="$1"
  GH_REPO="$2"
else
  read -rp "GitHub username (e.g., johndoe): " GH_USER
  read -rp "Repository name (e.g., github-starter): " GH_REPO
fi
URL="git@github.com:${GH_USER}/${GH_REPO}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi
printf "Origin set to %s\n" "$URL"

echo "Optional: push initial branch to GitHub"
echo "    git push -u origin main"
