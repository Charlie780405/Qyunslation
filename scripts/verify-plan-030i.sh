#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030i delivery gate. Do not nest full 028-030j suites.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
PDF2ZH_PY="${QYUNSLATION_PATCH_PY:-/usr/bin/python3}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
info() { printf 'INFO: %s\n' "$1"; }

show_failure_log() { [[ -f "$1" ]] && tail -n 60 "$1"; }

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

run_pass "030i runtime_probe compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/runtime_probe.py \
    qyunslation/structure/version_contract.py \
    scripts/_content_profile_ui.py \
    scripts/verify-runtime-deps.py

run_pass "030ic runtime dependency contract" "$STAGE_DIR/deps.log" \
  "$PY" "$ROOT/scripts/verify-runtime-deps.py"

if [[ -f "$ROOT/scripts/check-babeldoc-fidelity-033l.py" ]]; then
  run_pass "030id babeldoc patch signature" "$STAGE_DIR/babeldoc.log" \
    "$PDF2ZH_PY" "$ROOT/scripts/check-babeldoc-fidelity-033l.py"
else
  info "check-babeldoc-fidelity-033l.py missing, skipped"
fi

run_pass "030i runtime probe tests" "$STAGE_DIR/probe-tests.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_runtime_probe.py \
    tests/structure/test_plan030ia_ui_contract.py \
    tests/structure/test_plan030ib_manifest_download.py

run_pass "030ia GUI extension manifest regression" "$STAGE_DIR/gui-manifest.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_gui_extension_manifest.py

NOSAMPLE_XML="$STAGE_DIR/nosample.xml"
NOSAMPLE_LOG="$STAGE_DIR/nosample.log"
if env QYUNSLATION_SAMPLE_ROOT="$STAGE_DIR/absent-samples" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure --no-cov \
    --junitxml="$NOSAMPLE_XML" >"$NOSAMPLE_LOG" 2>&1; then
  if "$PY" - "$NOSAMPLE_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
assert not root.findall(".//failure")
assert not root.findall(".//error")
passed = sum(
    1
    for case in root.findall(".//testcase")
    if case.find("skipped") is None and case.find("failure") is None
)
assert passed >= 280, passed
PY
  then
    pass "structure suite green without runtime sample directory"
  else
    fail "structure suite regressed without runtime samples"
    show_failure_log "$NOSAMPLE_LOG"
  fi
else
  fail "structure suite failed without runtime samples"
  show_failure_log "$NOSAMPLE_LOG"
fi

PATCH_ORDER="$ROOT/docs/contracts/pdf2zh-patch-order.md"
SERVICE="$ROOT/scripts/pdf2zh.service"
if [[ -f "$PATCH_ORDER" && -f "$SERVICE" ]]; then
  missing=0
  while IFS= read -r script; do
    [[ -z "$script" ]] && continue
    if ! grep -q "$script" "$SERVICE"; then
      printf 'FAIL: %s missing from pdf2zh.service\n' "$script"
      missing=$((missing + 1))
    fi
  done < <(grep -oE 'apply-pdf2zh-[a-z0-9-]+\.py' "$PATCH_ORDER" | sort -u)
  if [[ "$missing" -eq 0 ]]; then
    pass "030id patch order doc matches service"
  else
    FAILURES=$((FAILURES + missing))
  fi
else
  info "patch order doc or service missing"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0 blocked=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
