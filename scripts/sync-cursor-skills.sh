#!/usr/bin/env bash
# 软链本仓 skills → ~/.cursor/skills/<slug>
# 禁止写入 ~/.cursor/skills-cursor/（Cursor 内置保留区）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/.cursor/skills"
DST="${HOME}/.cursor/skills"
mkdir -p "$DST"

for dir in "$SRC"/*; do
  [[ -d "$dir" ]] || continue
  slug=$(basename "$dir")
  [[ "$slug" == "skill-registry" ]] && continue
  target="$DST/$slug"
  if [[ -e "$target" || -L "$target" ]]; then
    if [[ -L "$target" ]]; then
      cur=$(readlink -f "$target" || true)
      want=$(readlink -f "$dir")
      if [[ "$cur" == "$want" ]]; then
        echo "ok: $slug"
        continue
      fi
      # 已指向别仓 → 告警跳过
      if [[ "$cur" != "$want" ]]; then
        echo "WARN: skip $slug already linked to $cur (want $want)"
        continue
      fi
    else
      echo "WARN: skip $slug exists and is not a symlink"
      continue
    fi
  fi
  ln -sfn "$dir" "$target"
  echo "linked: $target -> $dir"
done

echo "done (never write ~/.cursor/skills-cursor/)"
