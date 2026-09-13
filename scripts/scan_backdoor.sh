#!/usr/bin/env bash
# Local folderOpen / dropper scan (replaces the removed GitHub Actions workflow).
# Usage (from repo root, or any cwd — script cds to root):
#   ./scripts/scan_backdoor.sh
#   bash scripts/scan_backdoor.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

failed=0

echo "== Backdoor scan (local) =="
echo "repo: $ROOT"

# 1) Editor auto-run (folderOpen campaign)
if [ -d .vscode ] && grep -rInE 'folderOpen|allowAutomaticTasks' .vscode 2>/dev/null; then
  echo "FAIL: editor auto-run configuration under .vscode"
  failed=1
else
  echo "OK: no folderOpen / allowAutomaticTasks under .vscode"
fi

# 2) Known dropper paths
if droppers="$(git ls-files | grep -E '(^|/)\.github/setup\.js$|(^|/)fa-solid-500\.woff2$' || true)" \
  && [ -n "$droppers" ]; then
  echo "FAIL: known backdoor dropper path is tracked:"
  echo "$droppers"
  failed=1
else
  echo "OK: no tracked .github/setup.js or fa-solid-500.woff2"
fi

# 3) Text payloads disguised as fonts/images
disguised=0
while IFS= read -r path; do
  [ -z "$path" ] && continue
  [ -f "$path" ] || continue
  case "$(file -b "$path" 2>/dev/null || true)" in
    *text*)
      echo "FAIL: asset is text, not binary: $path"
      disguised=1
      ;;
  esac
done < <(git ls-files -- '*.woff' '*.woff2' '*.ttf' '*.eot' '*.png' '*.jpg' '*.jpeg' '*.gif' '*.ico' 2>/dev/null || true)

if [ "$disguised" -ne 0 ]; then
  failed=1
else
  echo "OK: no text-disguised font/image assets in git"
fi

if [ "$failed" -ne 0 ]; then
  echo "== RESULT: FAIL =="
  exit 1
fi

echo "== RESULT: PASS =="
exit 0
