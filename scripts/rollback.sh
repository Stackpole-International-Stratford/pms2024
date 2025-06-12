#!/usr/bin/env bash
set -euo pipefail

read -rp "Branch to roll back: " BRANCH
read -rp "How many commits back? " COUNT

git fetch origin
git checkout "$BRANCH"

echo
echo "1) Hard reset (rewrites history, will force-push)"
echo "2) Safe revert (creates undo commits, push normally)"
read -rp "Choose rollback method [1/2]: " METHOD

if [[ $METHOD == "1" ]]; then
  git reset --hard "HEAD~$COUNT"
  PUSH_CMD="git push --force-with-lease origin $BRANCH"
elif [[ $METHOD == "2" ]]; then
  git revert --no-edit "HEAD~$COUNT..HEAD"
  PUSH_CMD="git push origin $BRANCH"
else
  echo "No valid method chosen; exiting."
  exit 1
fi

echo
echo "Rollback done. About to run:"
echo "  $PUSH_CMD"
$PUSH_CMD
echo "✅ Push completed."
