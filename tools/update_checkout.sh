#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
cd "$(dirname "$0")/.."
trap 'status=$?; if [ "$status" -ne 0 ]; then echo "Update stopped; no local changes were discarded."; fi; read -r -p "Press Enter to close..." || true' EXIT
if [ -n "$(git status --porcelain)" ]; then
  echo "Commit or save your local changes before updating."
  exit 1
fi
case "$(git remote get-url origin)" in
  https://github.com/tonythewizard/fresh-fan-manager.git|https://github.com/tonythewizard/fresh-fan-manager|git@github.com:tonythewizard/fresh-fan-manager.git) ;;
  *) echo "Unexpected origin. Update manually after reviewing the remote."; exit 1 ;;
esac
branch=$(git symbolic-ref --short HEAD)
if [ "$branch" != main ]; then
  echo "Automatic checkout updates require the main branch."
  exit 1
fi
git pull --ff-only origin main
make update
echo "Update installed. Restart Fresh Fan Manager to use the new version."
