#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033 umbrella gate. Do not nest 028-030h.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-300}"
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

run_pass "PLAN-033a" "$STAGE_DIR/033a.log" bash scripts/verify-plan-033a.sh
run_pass "PLAN-033b" "$STAGE_DIR/033b.log" bash scripts/verify-plan-033b.sh
run_pass "PLAN-033c" "$STAGE_DIR/033c.log" bash scripts/verify-plan-033c.sh
run_pass "PLAN-033d" "$STAGE_DIR/033d.log" bash scripts/verify-plan-033d.sh
run_pass "PLAN-033e" "$STAGE_DIR/033e.log" bash scripts/verify-plan-033e.sh

run_pass "structure suite once" "$STAGE_DIR/structure.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_caption_anchors.py \
    tests/structure/test_table_protection.py \
    tests/structure/test_column_layout.py \
    tests/structure/test_unnumbered_objects.py \
    tests/structure/test_fixture_catalog.py

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
