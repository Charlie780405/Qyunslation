#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030j layout debt gate (D4 first). Do not nest full 030h.
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

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass "030j layout compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q qyunslation/structure/layout.py

run_pass "030j D4 poster gold samples" "$STAGE_DIR/poster.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_layout_gold_samples.py::test_poster_is_recognised_as_freeform \
    tests/structure/test_layout_gold_samples.py::test_poster_panels_keep_spatial_reading_order \
    tests/structure/test_layout_gold_samples.py::test_slide_aspect_short_circuit_still_guards_real_slides

run_pass "030j layout gold regression" "$STAGE_DIR/gold.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_layout_gold_samples.py

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
