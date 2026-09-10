#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-036 table policy unification + continued-table gold gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1\n'
  exit 1
fi

GOLD="$ROOT/tests/fixtures/structure/reference/cai-2025-table1-continued.pdf"
if [[ ! -f "$GOLD" ]]; then
  fail "CONTINUED_TABLE_GOLD_MISSING: $GOLD"
fi

run_pass "036 compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/table_cell_policy.py \
    qyunslation/structure/scan_docx.py \
    qyunslation/extensions/doc_image_policy.py \
    scripts/md_tables.py

run_pass "036 policy tests" "$STAGE_DIR/policy.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan036_policy_parity.py \
    tests/structure/test_plan036_docx_table_policy.py \
    tests/structure/test_plan036_continued_table_gold.py

run_pass "035 regression" "$STAGE_DIR/035.log" \
  bash "$ROOT/scripts/verify-plan-035.sh"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
