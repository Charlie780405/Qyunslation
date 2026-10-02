#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-076：AD 中英双向提示词、术语、QA 与上线证据总门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
FAILURES=0
BLOCKED=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-076-ad-bilingual-prompt-quality-system/README.md"
  "qyunslation/pipeline/ad_prompt.py"
  "qyunslation/pipeline/ad_termbase.py"
  "qyunslation/pipeline/ad_qa.py"
  "qyunslation/pipeline/ad_semantic.py"
  "glossaries/domain-ad.csv"
  "scripts/plan076-ad-eval.py"
  "tests/gold/ad/README.md"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= \
    tests/pipeline/test_plan076_ad_prompt.py \
    tests/pipeline/test_plan076_ad_qa.py \
    tests/pipeline/test_plan076_ad_termbase.py \
    tests/pipeline/test_plan076_ad_runtime.py \
    tests/pipeline/test_plan076_factory_prompt.py \
    tests/pipeline/test_plan076_semantic_qa.py \
    tests/scripts/test_plan076_eval.py \
    tests/api/test_plan076_ad_contract.py \
    tests/api/test_plan071b_launch_formats.py); then
    pass "PLAN-076 unit/contract tests"
  else
    fail "PLAN-076 pipeline tests"
  fi
else
  blocked "PLAN-076 Python interpreter unavailable"
fi

eval_rc=0
if [[ -x "$PY" ]]; then
  (cd "$ROOT" && "$PY" scripts/plan076-ad-eval.py --direction both) >"$ROOT/var/verify-plan-076-eval.log" 2>&1 || eval_rc=$?
  if [[ "$eval_rc" -eq 0 ]]; then
    pass "AD bilingual evaluation"
  elif [[ "$eval_rc" -eq 2 ]]; then
    blocked "AD bilingual evaluation corpus incomplete (see var/verify-plan-076-eval.log)"
  else
    fail "AD bilingual evaluation (see var/verify-plan-076-eval.log)"
  fi
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npm test -- --run >/dev/null && npm run type-check >/dev/null && npm run build >/dev/null); then
    pass "frontend tests/type-check/build"
  else
    fail "frontend tests/type-check/build"
  fi
else
  blocked "frontend dependencies unavailable"
fi

if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
  pass "chromium available for browser evidence"
else
  blocked "chromium unavailable; browser evidence remains unverified"
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
exit 0
