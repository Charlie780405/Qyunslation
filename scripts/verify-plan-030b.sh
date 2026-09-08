#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030b input adapters, normalization, production routing, and regression gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-300}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKERS=0
EXPECTED_REDS=0

cleanup() {
  rm -rf -- "$STAGE_DIR"
}
trap cleanup EXIT

cd "$ROOT" || exit 1

fail() {
  printf 'FAIL: %s\n' "$1"
  FAILURES=$((FAILURES + 1))
}

pass() {
  printf 'PASS: %s\n' "$1"
}

expected_red() {
  printf 'EXPECTED_RED: %s\n' "$1"
  EXPECTED_REDS=$((EXPECTED_REDS + 1))
}

blocked() {
  printf 'BLOCKED: %s\n' "$1"
  BLOCKERS=$((BLOCKERS + 1))
}

show_failure_log() {
  local log_path="$1"
  if [[ -f "$log_path" ]]; then
    tail -n 60 "$log_path"
  fi
}

run_pass() {
  local label="$1"
  local log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then
    pass "$label"
  else
    fail "$label"
    show_failure_log "$log_path"
  fi
}

if [[ ! -x "$PY" ]]; then
  blocked "Python runtime is unavailable at $PY"
  printf 'SUMMARY: FAIL expected_red=0 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

if [[ ! "$TEST_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  blocked "QYUNSLATION_VERIFY_TIMEOUT_SECONDS must be a positive integer"
  printf 'SUMMARY: FAIL expected_red=0 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

run_pass \
  "PLAN-030b modules compile" \
  "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure \
    qyunslation/converter/office.py \
    qyunslation/server/uploads.py \
    scripts/doc_image_prescan.py

run_pass \
  "focused input, normalization, canvas, prescan, and entry tests" \
  "$STAGE_DIR/focused.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --no-cov \
      tests/structure/test_input_detection.py \
      tests/structure/test_runtime_capabilities.py \
      tests/structure/test_canvas_adapters.py \
      tests/structure/test_office_normalization.py \
      tests/structure/test_input_preparation.py \
      tests/structure/test_prescan_input_routes.py \
      tests/structure/test_translation_entry.py \
      tests/structure/test_real_pdf_fixture.py

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
assert xfails == {
    "test_user_summary_reports_ljae439_semantic_figures_not_physical_regions",
    "test_pptx_picture_shape_is_emitted_as_a_translatable_object",
}, xfails
assert not root.findall(".//failure")
assert not root.findall(".//error")
PY
  then
    expected_red "only PLAN-030c semantic count and PLAN-030g PPT image execution remain XFAIL"
  else
    fail "structure XFAIL inventory changed"
    show_failure_log "$STRUCTURE_LOG"
  fi
else
  fail "structure suite failed"
  show_failure_log "$STRUCTURE_LOG"
fi

RUNXFAIL_XML="$STAGE_DIR/runxfail.xml"
RUNXFAIL_LOG="$STAGE_DIR/runxfail.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure/test_plan030_red_baselines.py \
    --runxfail --no-cov --junitxml="$RUNXFAIL_XML" >"$RUNXFAIL_LOG" 2>&1; then
  fail "--runxfail unexpectedly passed; the two downstream gaps are stale"
  show_failure_log "$RUNXFAIL_LOG"
else
  if "$PY" - "$RUNXFAIL_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
cases = root.findall(".//testcase")
failed = {case.attrib["name"] for case in cases if case.find("failure") is not None}
assert len(cases) == 6, len(cases)
assert failed == {
    "test_user_summary_reports_ljae439_semantic_figures_not_physical_regions",
    "test_pptx_picture_shape_is_emitted_as_a_translatable_object",
}, failed
assert not root.findall(".//error")
assert not root.findall(".//skipped")
PY
  then
    expected_red "--runxfail proves the exact two downstream gaps still fail"
  else
    fail "--runxfail differs from the exact two-failure baseline"
    show_failure_log "$RUNXFAIL_LOG"
  fi
fi

run_pass \
  "ljae439 TEST_FIXTURE_ONLY bytes, SHA-256, and ten canvases" \
  "$STAGE_DIR/ljae439.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q tests/structure/test_real_pdf_fixture.py --no-cov

run_pass \
  "full pytest regression excluding recorded archive failures" \
  "$STAGE_DIR/full.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov

# PLAN-032 已修好这三条历史红（原文件名清洗 + 归档 ID 前缀），不再是预期红
ARCHIVE_LOG="$STAGE_DIR/archive.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/test_pdf2zh_archive.py --no-cov >"$ARCHIVE_LOG" 2>&1; then
  pass "archive naming suite is green since PLAN-032"
else
  fail "archive naming suite regressed"
  show_failure_log "$ARCHIVE_LOG"
fi

if [[ "$FAILURES" -eq 0 && "$BLOCKERS" -eq 0 && "$EXPECTED_REDS" -eq 2 ]]; then
  printf 'SUMMARY: PASS expected_red=%d blocked=0 fail=0\n' "$EXPECTED_REDS"
  exit 0
fi

printf 'SUMMARY: FAIL expected_red=%d blocked=%d fail=%d\n' \
  "$EXPECTED_REDS" "$BLOCKERS" "$FAILURES"
exit 1
