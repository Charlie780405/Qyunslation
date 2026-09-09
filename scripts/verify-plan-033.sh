#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-033 umbrella: subgates + final mono/dual PDF. Do not nest 028-030h.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-300}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }
show_failure_log() { [[ -f "$1" ]] && tail -n 40 "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then
    if grep -q '^SUMMARY: BLOCKED' "$log_path"; then blocked "$label"
    else pass "$label"
    fi
  else
    if grep -q '^SUMMARY: BLOCKED' "$log_path"; then blocked "$label"
    else fail "$label"; show_failure_log "$log_path"
    fi
  fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

for gate in 033a 033b 033c 033d 033e 033g 033h 033i 033j 033k 033l; do
  run_pass "PLAN-$gate" "$STAGE_DIR/$gate.log" bash "$ROOT/scripts/verify-plan-$gate.sh"
done

run_pass "structure suite once" "$STAGE_DIR/structure.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_caption_anchors.py \
    tests/structure/test_table_protection.py \
    tests/structure/test_column_layout.py \
    tests/structure/test_unnumbered_objects.py \
    tests/structure/test_fixture_catalog.py \
    tests/structure/test_execution_contract_033g.py \
    tests/structure/test_plan033h_references_style.py \
    tests/structure/test_plan033i_table_structure.py \
    tests/structure/test_plan033j_table_translate.py \
    tests/structure/test_plan033k_role_fitter.py

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
