#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-035 table digit protection + cross-page continuation gate.
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

run_pass "035 compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/table_cell_policy.py \
    qyunslation/structure/table_translate.py \
    qyunslation/structure/scan_pdf.py \
    scripts/pdf_table_translate.py

run_pass "035 scanner version" "$STAGE_DIR/version.log" \
  "$PY" -c "from qyunslation.structure.scan_pdf import PDF_STRUCTURE_SCANNER_VERSION; assert PDF_STRUCTURE_SCANNER_VERSION == '1.8.0'"

run_pass "035 digit policy tests" "$STAGE_DIR/digit.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan035_digit_policy.py

run_pass "035 continuation tests" "$STAGE_DIR/cont.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan035_continuation.py

run_pass "033j table translate regression" "$STAGE_DIR/033j.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan033j_table_translate.py

run_pass "030-table regression" "$STAGE_DIR/030table.log" \
  bash "$ROOT/scripts/verify-plan-030-table.sh"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
