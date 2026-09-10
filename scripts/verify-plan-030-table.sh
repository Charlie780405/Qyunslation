#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030-table PDF cell grid gate. Do not nest full 030d–030i suites.
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

run_pass "030-table compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/table_structure.py \
    qyunslation/structure/scan_pdf.py \
    scripts/spike-plan030-table-task0.py

run_pass "030-table Task 0 spike" "$STAGE_DIR/spike.log" \
  "$PY" "$ROOT/scripts/spike-plan030-table-task0.py"

run_pass "030-table protection regression" "$STAGE_DIR/protect.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_table_protection.py

run_pass "030-table grid dimensions" "$STAGE_DIR/grid.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan030_table_geometry.py

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
