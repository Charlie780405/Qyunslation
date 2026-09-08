#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030g PPT/PPTX dual-mode gate. Do not nest 028–030f.
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

run_pass "PLAN-030g modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/scan_pptx.py \
    qyunslation/workflow/pptx_workflow.py \
    qyunslation/translator/ai_translator/pptx_translator.py

run_pass "pptx scan + QY030-PPT-001" "$STAGE_DIR/scan-pptx.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_scan_pptx.py \
    tests/structure/test_plan030_red_baselines.py::test_pptx_picture_shape_is_emitted_as_a_translatable_object

STRUCTURE_XML="$STAGE_DIR/structure.xml"
STRUCTURE_LOG="$STAGE_DIR/structure.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure --no-cov \
    --junitxml="$STRUCTURE_XML" >"$STRUCTURE_LOG" 2>&1; then
  if "$PY" - "$STRUCTURE_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
xfails = {
    case.attrib["name"]
    for case in root.findall(".//testcase")
    if (node := case.find("skipped")) is not None
    and node.attrib.get("type") == "pytest.xfail"
}
assert xfails == set(), xfails
assert not root.findall(".//failure")
assert not root.findall(".//error")
PY
  then
    pass "structure suite has no XFAIL"
  else
    fail "structure XFAIL inventory changed"
    show_failure_log "$STRUCTURE_LOG"
  fi
else
  fail "structure suite failed"
  show_failure_log "$STRUCTURE_LOG"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
