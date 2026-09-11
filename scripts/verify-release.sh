#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# Release gate: orchestrates delivery-critical verify-plan scripts.
# Does not replace domain suites; chains gates that must pass before deploy.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STRICT_SAMPLE="${QYUNSLATION_RELEASE_STRICT_SAMPLE:-0}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
PASSED=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; PASSED=$((PASSED + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }
info() { printf 'INFO: %s\n' "$1"; }

run_gate() {
  local label="$1" script="$2" log_path="$3"
  local mode="${4:-required}"
  if [[ ! -f "$ROOT/$script" ]]; then
    fail "$label (missing $script)"
    return
  fi
  if [[ ! -x "$ROOT/$script" ]]; then
    chmod +x "$ROOT/$script" || true
  fi
  set +e
  env QYUNSLATION_VERIFY_PY="$PY" bash "$ROOT/$script" >"$log_path" 2>&1
  local status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    pass "$label"
    return
  fi
  tail -n 30 "$log_path"
  if [[ "$status" -eq 2 && "$mode" == "sample" && "$STRICT_SAMPLE" != "1" ]]; then
    blocked "$label (sample-dependent; set QYUNSLATION_RELEASE_STRICT_SAMPLE=1 to hard-fail)"
    return
  fi
  if [[ "$status" -eq 2 ]]; then
    blocked "$label"
    return
  fi
  fail "$label (exit $status)"
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=1 gates=0\n'
  exit 1
fi

info "release gate root=$ROOT py=$PY strict_sample=$STRICT_SAMPLE"

run_gate "030i delivery" "scripts/verify-plan-030i.sh" "$STAGE_DIR/030i.log" required
run_gate "035 table execution" "scripts/verify-plan-035.sh" "$STAGE_DIR/035.log" required
run_gate "036 table policy" "scripts/verify-plan-036.sh" "$STAGE_DIR/036.log" required
run_gate "037 table observability" "scripts/verify-plan-037-table-observability.sh" "$STAGE_DIR/037.log" required
run_gate "038 gap closure" "scripts/verify-plan-038.sh" "$STAGE_DIR/038.log" required
run_gate "039 glossary governance" "scripts/verify-plan-039.sh" "$STAGE_DIR/039.log" required
run_gate "040 upload auth ux" "scripts/verify-plan-040.sh" "$STAGE_DIR/040.log" required
run_gate "041 regulatory form fidelity" "scripts/verify-plan-041.sh" "$STAGE_DIR/041.log" sample
run_gate "042 regulatory translation quality" "scripts/verify-plan-042.sh" "$STAGE_DIR/042.log" sample
run_gate "030-table geometry" "scripts/verify-plan-030-table.sh" "$STAGE_DIR/030-table.log" required
run_gate "033l pdf final" "scripts/verify-plan-033l.sh" "$STAGE_DIR/033l.log" sample

printf '\n--- release gate rollup ---\n'
printf 'passed=%d failed=%d blocked=%d\n' "$PASSED" "$FAILURES" "$BLOCKED"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%d blocked=%d\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0
