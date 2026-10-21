#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-086：语言资产核心闭环门禁。三态：PASS / FAIL / BLOCKED。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
FAILURES=0
BLOCKED=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

for path in \
  "docs/plans/PLAN-086-language-assets-quality-system/README.md" \
  "docs/plans/PLAN-086-language-assets-quality-system/PLAN-086-language-assets-quality-system.md" \
  "alembic/versions/086a0001_language_assets.py" \
  "qyunslation/language_assets.py" \
  "tests/api/test_plan086_language_assets.py"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider \
      tests/api/test_plan086_language_assets.py \
      tests/persist/test_plan058_api.py \
      tests/persist/test_plan058_termbase.py \
      tests/api/test_plan076_ad_contract.py); then
    pass "PLAN-086 backend tests"
  else
    fail "PLAN-086 backend tests"
  fi
else
  blocked "Python interpreter unavailable"
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npm run type-check >/dev/null && npx vitest run src/next >/dev/null); then
    pass "frontend type-check and vitest"
  else
    fail "frontend type-check or vitest"
  fi
  if (cd "$ROOT/frontend" && npm run build >/dev/null); then
    pass "frontend build"
  else
    fail "frontend build"
  fi
else
  blocked "frontend dependencies unavailable"
fi

blocked "专家盲评金标、高风险术语 recall/误阻断率、shadow→pilot→on 灰度尚未执行"
blocked "生产迁移与真实租户浏览器走查尚未执行"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
