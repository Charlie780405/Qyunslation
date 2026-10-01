#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-074：作者保护、单位审核、术语闭环与乱码门禁验收。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
FAILURES=0
BLOCKED=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "alembic/versions/074a0001_plan074_review_terms.py"
  "qyunslation/structure/frontmatter.py"
  "qyunslation/structure/text_sanitize.py"
  "qyunslation/structure/translation_trace.py"
  "qyunslation/workbench/term_extract.py"
  "frontend/src/next/components/AffiliationReviewPanel.vue"
  "frontend/src/next/components/TermReviewPanel.vue"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan074_frontmatter.py \
    tests/structure/test_plan074_translation_trace.py \
    tests/structure/test_plan045_sanitize.py \
    tests/pipeline/test_plan071e_pdf_inspect.py \
    tests/workbench/test_plan074_term_extract.py \
    tests/workbench/test_plan060_bridge.py \
    tests/persist/test_plan074_migration.py \
    tests/api/test_plan071e_review_gate.py \
    tests/api/test_plan071e_real_qa_gate.py \
    tests/scripts/test_plan071_patch_fingerprint.py); then
    pass "backend/API/migration/patch tests"
  else
    fail "backend/API/migration/patch tests"
  fi

  if (cd "$ROOT" && "$PY" - <<'PY'
from scripts.plan071_patch_fingerprint import build_report, resolve_site

report = build_report(resolve_site(None))
row = next(item for item in report["patches"] if item["patch_id"] == "074-frontmatter-trace")
raise SystemExit(0 if row["present"] else 2)
PY
  ); then
    pass "installed BabelDOC PLAN-074 hook"
  else
    blocked "installed BabelDOC PLAN-074 hook not active; run apply-pdf2zh-045c-sanitize.py before live rerun"
  fi
else
  fail "Python interpreter unavailable; set QYUNSLATION_VERIFY_PY"
fi

if [[ -d "$ROOT/frontend/node_modules" ]] && command -v npm >/dev/null 2>&1; then
  if (cd "$ROOT/frontend" && npm test --silent); then
    pass "frontend Vitest and axe"
  else
    fail "frontend Vitest and axe"
  fi
  if (cd "$ROOT/frontend" && npm run type-check --silent); then
    pass "frontend type-check"
  else
    fail "frontend type-check"
  fi
  if (cd "$ROOT/frontend" && npm run build --silent); then
    pass "frontend production build"
  else
    fail "frontend production build"
  fi
else
  blocked "frontend verification skipped: npm or node_modules unavailable"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
