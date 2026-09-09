#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033b table geometry gate. Do not nest 028-030h.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-180}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
show_failure_log() { [[ -f "$1" ]] && tail -n 40 "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; show_failure_log "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass "PLAN-033b modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q qyunslation/structure/tables.py qyunslation/structure/scan_pdf.py

run_pass "scanner version is 1.4.0" "$STAGE_DIR/version.log" \
  "$PY" -c "from qyunslation.structure.scan_pdf import PDF_STRUCTURE_SCANNER_VERSION; assert PDF_STRUCTURE_SCANNER_VERSION == '1.4.0'"

run_pass "table geometry and catalog" "$STAGE_DIR/tables.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_table_protection.py \
    tests/structure/test_fixture_catalog.py

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
