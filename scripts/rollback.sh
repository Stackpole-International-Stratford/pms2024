#!/usr/bin/env bash
set -euo pipefail

# 1) Read inputs
read -rp "Branches to roll back (comma-separated): " BRANCHES
read -rp "How many commits back? " COUNT

# 2) Pick method once
echo
echo "1) Hard reset (rewrites history, will force-push)"
echo "2) Safe revert (creates undo commits, push normally)"
read -rp "Choose rollback method [1/2]: " METHOD

case "$METHOD" in
  1)
    ROLLBACK_CMD="git reset --hard HEAD~$COUNT"
    PUSH_FLAGS="--force-with-lease"
    ;;
  2)
    ROLLBACK_CMD="git revert --no-edit HEAD~$COUNT..HEAD"
    PUSH_FLAGS=""
    ;;
  *)
    echo "Invalid choice; exiting." >&2
    exit 1
    ;;
esac

# 3) Loop over each branch
IFS=',' read -ra BR_ARR <<< "$BRANCHES"
for raw in "${BR_ARR[@]}"; do
  BRANCH="$(echo "$raw" | xargs)"   # trim whitespace
  echo
  echo "▶ Processing branch: $BRANCH"
  git fetch origin
  git checkout "$BRANCH"

  echo "  ↪ $ROLLBACK_CMD"
  $ROLLBACK_CMD

  echo "  ↪ git push $PUSH_FLAGS origin $BRANCH"
  git push $PUSH_FLAGS origin "$BRANCH"
done

echo
echo "✅ All done."
