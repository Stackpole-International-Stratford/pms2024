#!/usr/bin/env bash
set -euo pipefail

# 1) Read inputs
read -rp "Branch to roll back: " BRANCH
read -rp "How many commits back? " COUNT

# 2) Fetch & switch
git fetch origin
echo "Checking out branch '$BRANCH'..."
git checkout "$BRANCH"

# 3a) Option A: hard reset (rewrites history — you will need a force-push)
echo
echo "About to run: git reset --hard HEAD~$COUNT"
read -rp "Proceed with HARD reset? This rewrites history! [y/N] " yn
if [[ $yn =~ ^[Yy]$ ]]; then
  git reset --hard "HEAD~$COUNT"
  echo "Branch is now at HEAD~$COUNT. You can test locally and then 'git push --force'."
  exit 0
fi

# 3b) Option B: revert commits (safe for shared branches)
echo
echo "About to run: git revert --no-commit HEAD~$COUNT..HEAD"
read -rp "Proceed with safe REVERT of the last $COUNT commits? [y/N] " yn2
if [[ $yn2 =~ ^[Yy]$ ]]; then
  git revert --no-edit "HEAD~$COUNT..HEAD"
  echo "Revert commit(s) created. Review, then 'git push'."
  exit 0
fi

echo "No action taken."
exit 1
