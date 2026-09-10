#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-041 regulatory form fidelity gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  elif [[ -x /home/dev/qyunslation/.venv/bin/python ]]; then
    PY=/home/dev/qyunslation/.venv/bin/python
  else
    PY="$ROOT/.venv/bin/python"
  fi
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

[[ -f "$ROOT/docs/plans/PLAN-041-pdf-regulatory-form-fidelity/PLAN-041-pdf-regulatory-form-fidelity.md" ]] \
  && pass "PLAN-041 charter" || fail "missing PLAN-041 charter"
for f in PLAN-041a-language-routing.md PLAN-041b-captionless-form-tables.md \
         PLAN-041c-cell-translation-writeback.md PLAN-041d-quality-gates.md; do
  [[ -f "$ROOT/docs/plans/PLAN-041-pdf-regulatory-form-fidelity/$f" ]] && pass "$f" || fail "missing $f"
done

run_pass "041 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/table_qc.py \
  qyunslation/structure/table_translate.py \
  qyunslation/structure/table_writeback.py \
  qyunslation/structure/role_fitter.py \
  scripts/pdf_table_translate.py

run_pass "041 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 180s "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan041_language_routing.py \
    tests/structure/test_plan041_captionless_forms.py \
    tests/structure/test_plan041_table_writeback.py \
    tests/structure/test_plan041_quality_gates.py \
    tests/structure/test_plan033k_role_fitter.py

if [[ -n "${QYUNSLATION_PLAN041_SAMPLE:-}" && -f "$QYUNSLATION_PLAN041_SAMPLE" ]]; then
  run_pass "041 real sample gold" "$STAGE_DIR/sample.log" \
    timeout --signal=INT --kill-after=10s 180s env \
    QYUNSLATION_PLAN041_SAMPLE="$QYUNSLATION_PLAN041_SAMPLE" \
    "$PY" -m pytest -q -o addopts= -k "plan041_real_sample"
else
  blocked "QYUNSLATION_PLAN041_SAMPLE missing"
fi

[[ -f "$ROOT/docs/walkthroughs/WT-041-pdf-regulatory-form-fidelity.md" ]] \
  && pass "WT-041" || fail "missing WT-041"
[[ -f "$ROOT/.cursor/skills/pdf-regulatory-form-fidelity/SKILL.md" ]] \
  && pass "SK-Q003 skill" || fail "missing SK-Q003"
if grep -q 'SK-Q003' "$ROOT/.cursor/skills/skill-registry/registry.md"; then
  pass "SK-Q003 registered"
else
  fail "SK-Q003 not in registry"
fi

if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=%d\n' "$BLOCKED" "$FAILURES"
  exit 2
fi
if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
