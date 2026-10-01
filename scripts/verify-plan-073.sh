#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-073：质量门禁、模型分级与自免术语闭环验收。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
FAILURES=0
BLOCKED=0

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-073-quality-gate-domain-terms/README.md"
  "docs/walkthroughs/WT-073-quality-gate-domain-terms.md"
  "alembic/versions/073a0001_quality_gate_domain_terms.py"
  "qyunslation/workbench/runtime_config.py"
  "qyunslation/workbench/term_inject.py"
  "qyunslation/workbench/term_extract.py"
  "glossaries/domain-autoimmune.csv"
  "scripts/plan073-domain-eval.py"
)

for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

grep -q 'requalify' "$ROOT/qyunslation/api/v1.py" && pass "requalify endpoint" || fail "requalify endpoint"
grep -q 'term-candidates' "$ROOT/qyunslation/api/v1.py" && pass "term candidates endpoint" || fail "term candidates endpoint"
grep -q 'apply_model_snapshot' "$ROOT/qyunslation/workbench/runtime_config.py" && pass "runtime model config" || fail "runtime model config"

if [[ -x "$PY" ]]; then
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= \
    tests/persist/test_plan073_migration.py \
    tests/test_glossary/test_plan073_resolver_case.py \
    tests/pipeline/test_plan073_term_snapshot.py \
    tests/test_glossary/test_plan058_resolver.py) >"$ROOT/var/verify-plan-073-pytest.log" 2>&1; then
    pass "pytest plan073"
  else
    fail "pytest plan073 (see var/verify-plan-073-pytest.log)"
  fi
  eval_rc=0
  (cd "$ROOT" && "$PY" scripts/plan073-domain-eval.py) >"$ROOT/var/verify-plan-073-eval.log" 2>&1 || eval_rc=$?
  if [[ "$eval_rc" -eq 0 ]]; then
    pass "domain eval"
  elif [[ "$eval_rc" -eq 2 ]]; then
    blocked "domain eval missing machine corpus for some gold samples (see var/verify-plan-073-eval.log)"
  else
    fail "domain eval (see var/verify-plan-073-eval.log)"
  fi
else
  blocked "pytest plan073 (venv python missing)"
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npm test --silent) >"$ROOT/var/verify-plan-073-vitest.log" 2>&1; then
    pass "frontend vitest"
  else
    fail "frontend vitest (see var/verify-plan-073-vitest.log)"
  fi
else
  blocked "frontend vitest (node_modules missing)"
fi

if grep -q '^QYUNSLATION_DEEPSEEK_API_KEY=' /home/dev/pdf2zh/office.env 2>/dev/null; then
  pass "deepseek key configured"
else
  blocked "deepseek key not configured"
fi

if compgen -G "$ROOT/docs/evidence/plan073-074/*.png" >/dev/null; then
  pass "browser evidence screenshots present"
else
  blocked "browser evidence (add PNG under docs/evidence/plan073-074/)"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  echo "SUMMARY: FAIL fail=$FAILURES blocked=$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  echo "SUMMARY: BLOCKED fail=0 blocked=$BLOCKED"
  exit 2
fi
echo "SUMMARY: PASS fail=0 blocked=0"
exit 0
