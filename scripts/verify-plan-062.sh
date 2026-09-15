#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-062：术语工作台准确度与自动进化三态门禁。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

if [[ ! -x "$PY" ]]; then
  fail "Python interpreter unavailable; set QYUNSLATION_VERIFY_PY"
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-062-termbase-evolution"
for required in \
  "$PLAN_DIR/README.md" \
  "$PLAN_DIR/PLAN-062a-seed-and-purge.md" \
  "$PLAN_DIR/PLAN-062b-candidate-screen.md" \
  "$PLAN_DIR/PLAN-062c-paragraph-align.md" \
  "$PLAN_DIR/PLAN-062d-no-recurring-pending.md" \
  "$PLAN_DIR/PLAN-062e-concept-picker.md" \
  "$PLAN_DIR/PLAN-062f-nav-and-progress.md" \
  "$PLAN_DIR/PLAN-062g-verification-delivery.md" \
  "$ROOT/docs/walkthroughs/WT-062-termbase-evolution.md" \
  "$ROOT/qyunslation/glossary/term_screen.py" \
  "$ROOT/scripts/plan062-purge-stale-candidates.py"; do
  [[ -f "$required" ]] && pass "static $(basename "$required")" || fail "missing $required"
done

grep -q 'PLAN-062-termbase-evolution' "$ROOT/docs/plans/README.md" \
  && pass "plans index PLAN-062" || fail "plans index missing PLAN-062"
grep -Eq 'version = "06[23]-v[0-9]+"' "$ROOT/glossaries/term-candidate-rules.toml" \
  && pass "rules version present" || fail "rules version missing"
grep -q '_window_cjk' "$ROOT/qyunslation/workbench/term_align.py" \
  && fail "window heuristic still present" || pass "window heuristic removed"
grep -q 'status="applied" if applied else "violation"' \
  "$ROOT/qyunslation/workbench/bridge.py" \
  && pass "curated miss writes violation" || fail "curated miss still pending"

if "$PY" -m compileall -q \
  qyunslation/workbench \
  qyunslation/glossary/candidate_rules.py \
  qyunslation/glossary/term_screen.py \
  scripts/plan062-purge-stale-candidates.py \
  scripts/apply-pdf2zh-060-termbase-workbench.py; then
  pass "PLAN-062 modules compile"
else
  fail "PLAN-062 modules compile"
fi

if "$PY" -m pytest -q --no-cov \
  tests/workbench/test_plan062_purge.py \
  tests/glossary/test_plan062_term_screen.py \
  tests/workbench/test_plan062_paragraph_align.py \
  tests/workbench/test_plan062_no_recurring_pending.py \
  tests/ui/test_plan062_workbench_nav.py \
  tests/structure/test_plan062_progress.py \
  tests/workbench/test_plan061_candidate_rules.py \
  tests/workbench/test_plan061_term_align.py \
  tests/ui/test_plan061_workbench_patch.py \
  tests/workbench/test_plan060_evidence.py \
  tests/workbench/test_plan060_bridge.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "PLAN-062 focused pytest"
else
  fail "PLAN-062 focused pytest"
  tail -n 80 "$STAGE_DIR/pytest.log" || true
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%s fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0
