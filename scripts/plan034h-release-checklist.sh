#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-034h：发布清单（只读指纹；可选 --write 落盘）。
# 回滚：git checkout <prev-sha> → 再跑本脚本 → bash scripts/deploy-translate-stack.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRITE=0
OUT_DIR="$ROOT/artifacts"
cd "$ROOT" || exit 1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --write) WRITE=1; shift ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    -h|--help)
      printf 'Usage: %s [--write] [--out-dir DIR]\n' "$0"
      exit 0
      ;;
    *) printf 'unknown arg: %s\n' "$1" >&2; exit 2 ;;
  esac
done

sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
short="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
branch="$(git branch --show-current 2>/dev/null || echo unknown)"
dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

alembic_head="unknown"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  alembic_head="$("$ROOT/.venv/bin/python" - <<'PY' 2>/dev/null || echo unknown
from pathlib import Path
heads = sorted(Path("alembic/versions").glob("*.py"))
print(heads[-1].name if heads else "none")
PY
)"
fi

img="$ROOT/qyunslation/extensions/image_translate.py"
local_fp="missing"
if [[ -f "$img" ]]; then
  local_fp="$(python3 - <<PY
import hashlib
from pathlib import Path
print(hashlib.sha256(Path("$img").read_bytes()).hexdigest()[:12])
PY
)"
fi

schema="034h"
{
  printf 'PLAN-034h release checklist\n'
  printf 'generated_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'git_sha=%s\n' "$sha"
  printf 'git_short=%s\n' "$short"
  printf 'git_branch=%s\n' "$branch"
  printf 'git_dirty_files=%s\n' "$dirty"
  printf 'alembic_latest_file=%s\n' "$alembic_head"
  printf 'schema_label=%s\n' "$schema"
  printf 'sidecar_image_translate_fp12=%s\n' "$local_fp"
  printf 'deploy_hint=bash scripts/deploy-translate-stack.sh\n'
  printf 'rollback_steps=\n'
  printf '  1. git checkout <previous-sha>\n'
  printf '  2. bash scripts/plan034h-release-checklist.sh --write\n'
  printf '  3. bash scripts/deploy-translate-stack.sh\n'
} | tee /tmp/plan034h-checklist.txt

if [[ "$WRITE" == "1" ]]; then
  mkdir -p "$OUT_DIR"
  dest="$OUT_DIR/plan034h-release-${short}.txt"
  cp /tmp/plan034h-checklist.txt "$dest"
  printf 'wrote %s\n' "$dest" >&2
fi

exit 0
