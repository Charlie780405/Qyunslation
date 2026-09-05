#!/usr/bin/env bash
# 校验本仓 .cursor/skills 与 registry 一致
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REG="$ROOT/.cursor/skills/skill-registry/registry.md"
SKILLS="$ROOT/.cursor/skills"

pass=0
fail=0
check() {
  local d="$1"; shift
  if "$@"; then echo "PASS: $d"; pass=$((pass+1)); else echo "FAIL: $d"; fail=$((fail+1)); fi
}

check "registry 存在" test -f "$REG"
# slug 目录（排除 skill-registry）
mapfile -t dirs < <(find "$SKILLS" -mindepth 1 -maxdepth 1 -type d ! -name skill-registry | sort)
# registry 表行
mapfile -t rows < <(grep -E '^\| SK-Q[0-9]+' "$REG" || true)
check "registry 行数 == skill 目录数" test "${#rows[@]}" -eq "${#dirs[@]}"

ids=()
for row in "${rows[@]}"; do
  id=$(echo "$row" | awk -F'|' '{print $2}' | xargs)
  slug=$(echo "$row" | awk -F'|' '{print $3}' | xargs)
  ids+=("$id")
  check "slug 目录 $slug" test -d "$SKILLS/$slug"
  check "SKILL.md $slug" test -f "$SKILLS/$slug/SKILL.md"
  check "description 非空 $slug" grep -qE '^description:' "$SKILLS/$slug/SKILL.md"
  lines=$(wc -l < "$SKILLS/$slug/SKILL.md")
  check "SKILL.md ≤200 行 $slug" test "$lines" -le 200
done

# SK-ID 唯一
uniq_n=$(printf '%s\n' "${ids[@]}" | sort -u | wc -l)
check "SK-ID 唯一" test "$uniq_n" -eq "${#ids[@]}"

# 禁止把目标写到 skills-cursor（注释里提及「禁止」即可）
if [[ -f "$ROOT/scripts/sync-cursor-skills.sh" ]]; then
  check "sync 提及禁止 skills-cursor" grep -q 'skills-cursor' "$ROOT/scripts/sync-cursor-skills.sh"
  check "sync 无 ln 到 skills-cursor" bash -c "! grep -E 'ln .*skills-cursor' '$ROOT/scripts/sync-cursor-skills.sh'"
fi

echo "RESULT: $pass pass, $fail fail"
[[ "$fail" -eq 0 ]]
