#!/usr/bin/env bash
#
# Rejects merge commits that introduce content no parent had.
#
# Every backdoor in this repo arrived through a merge commit -- never through a
# normal commit. Two shapes were used:
#
#   1. Evil merge. The merge tree contains a blob present in neither parent, so
#      the pull request diff against main looks innocent.
#
#   2. Reverse no-op merge. Where one parent is an ancestor of the other, git
#      guarantees the merge tree equals the descendant's tree. These merges
#      produce a different tree anyway -- which is how pull requests literally
#      named `security/strip-folderopen-backdoor` (#36), `security/strip-
#      folderopen-after-42` (#42) and `#44` reintroduced the .vscode folderOpen
#      task and the fa-solid-500.woff2 dropper they claimed to remove.
#
# Both are mechanically detectable, so this checks invariants instead of payload
# strings. The payload is regenerated on every injection, so string matching
# alone always lags a rotation.
#
# Usage:
#   scripts/check_merge_integrity.sh                 # merges in origin/main..HEAD
#   scripts/check_merge_integrity.sh <range>         # merges in <range>
#   scripts/check_merge_integrity.sh <from> <to>     # merges in <from>..<to>
#   scripts/check_merge_integrity.sh --all           # every merge reachable from HEAD

set -uo pipefail

# Merges made by GitHub's own merge button are web-flow signed and committed by
# this identity. A merge pushed from a local machine carries a human committer.
GITHUB_COMMITTER_EMAIL='noreply@github.com'

# Optional allowlist, one email per line, for teams that intentionally merge
# locally. Anything listed here is accepted in addition to GitHub's committer.
ALLOWLIST_FILE='.github/trusted-merge-committers'

failed=0

report() {
  printf '\n%s\n' "$1" >&2
  failed=1
}

allowed_committer() {
  local email="$1"
  [ "$email" = "$GITHUB_COMMITTER_EMAIL" ] && return 0
  [ -f "$ALLOWLIST_FILE" ] || return 1
  awk -F'#' '{print $1}' "$ALLOWLIST_FILE" \
    | tr -d '[:space:]' \
    | grep -qix -- "$email"
}

# Resolve the range to scan.
case "${1:-}" in
  '')
    if git rev-parse --verify -q origin/main >/dev/null 2>&1; then
      range='origin/main..HEAD'
    else
      range='--all'
    fi
    ;;
  --all)
    range='--all'
    ;;
  *)
    if [ "$#" -ge 2 ]; then
      range="$1..$2"
    else
      range="$1"
    fi
    ;;
esac

# Fail closed. An unresolvable endpoint means git rev-list returns nothing, which
# would otherwise read as "no merges to inspect" and pass silently.
if [ "$range" != '--all' ]; then
  from_ref=${range%%..*}
  to_ref=${range##*..}
  for ref in "$from_ref" "$to_ref"; do
    if ! git rev-parse --verify -q "$ref^{commit}" >/dev/null 2>&1; then
      printf '\nMerge integrity check could not resolve %s in range %s.\n' "$ref" "$range" >&2
      printf 'Refusing to pass without inspecting. Fetch the missing history or fix the range.\n' >&2
      exit 1
    fi
  done
fi

merges=()
while IFS= read -r sha; do
  [ -n "$sha" ] && merges+=("$sha")
done < <(git rev-list --merges "$range" 2>/dev/null)

if [ "${#merges[@]}" -eq 0 ]; then
  echo "Merge integrity check passed (no merges in range '$range')."
  exit 0
fi

for merge in "${merges[@]}"; do
  # `git rev-list --parents` gives "<commit> <p1> <p2> [<p3>...]".
  parents=$(git rev-list --parents -n 1 "$merge")
  p1=$(printf '%s\n' "$parents" | awk '{print $2}')
  p2=$(printf '%s\n' "$parents" | awk '{print $3}')

  [ -n "$p2" ] || continue

  merge_tree=$(git rev-parse "$merge^{tree}")

  short=$(git log -1 --format='%h %s' "$merge")

  # --- Check 1: reverse no-op merge -----------------------------------------
  # If p1 is an ancestor of p2, the merge tree must equal p2's tree exactly.
  if git merge-base --is-ancestor "$p1" "$p2" 2>/dev/null; then
    expected_tree=$(git rev-parse "$p2^{tree}")
    if [ "$merge_tree" != "$expected_tree" ]; then
      report "Reverse no-op merge detected: $short
       $p1 is an ancestor of $p2, so this merge's tree must be identical to
       $p2's tree. It is not -- the merge silently kept content the branch had
       removed. Files differing from the expected tree:"
      git diff --name-only "$p2" "$merge" | sed 's/^/         /' >&2
    fi
  fi

  # --- Check 2: the mirror case ---------------------------------------------
  if git merge-base --is-ancestor "$p2" "$p1" 2>/dev/null; then
    expected_tree=$(git rev-parse "$p1^{tree}")
    if [ "$merge_tree" != "$expected_tree" ]; then
      report "Reverse no-op merge detected: $short
       $p2 is an ancestor of $p1, so this merge's tree must be identical to
       $p1's tree. It is not. Files differing from the expected tree:"
      git diff --name-only "$p1" "$merge" | sed 's/^/         /' >&2
    fi
  fi

  # --- Check 3: is the merge a faithful merge at all? -----------------------
  # Recompute what a clean merge of the two parents produces and compare. A merge
  # that conflicts legitimately differs, so only a *clean* recomputation is
  # conclusive; git merge-tree exits non-zero when it hits conflicts.
  # `--write-tree` needs git >= 2.38, so degrade quietly on older git.
  if auto_tree=$(git merge-tree --write-tree "$p1" "$p2" 2>/dev/null); then
    if [ -n "$auto_tree" ] && [ "$merge_tree" != "$auto_tree" ]; then
      report "Merge is not a faithful merge: $short
       Merging $p1 and $p2 cleanly produces tree $auto_tree, but this merge
       committed tree $merge_tree. Content was altered or added by hand during
       the merge. Files differing from a clean merge:"
      git diff --name-only "$auto_tree" "$merge" | sed 's/^/         /' >&2
    fi
  fi

  # --- Check 4: committer identity ------------------------------------------
  committer_email=$(git log -1 --format='%ce' "$merge")
  if ! allowed_committer "$committer_email"; then
    report "Unrecognised merge committer: $short
       Committer is '$committer_email'. Merges made through GitHub's merge
       button are committed by <$GITHUB_COMMITTER_EMAIL> and web-flow signed.
       If merging locally is intentional, add the identity to $ALLOWLIST_FILE."
  fi
done

if [ "$failed" -ne 0 ]; then
  printf '\nMerge integrity check failed.\n' >&2
  printf 'Do not push this. Inspect the merges above, then re-create them so this passes.\n' >&2
  exit 1
fi

echo "Merge integrity check passed (${#merges[@]} merges in '$range')."
