#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030c unified semantic scan, caption-driven regions, and table-page guard.
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
  "PLAN-030c modules compile" \
  "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure \
    scripts/doc_image_prescan.py \
    scripts/pdf_figure_crop.py \
    scripts/pdf_image_translate.py

run_pass \
  "focused caption, region, scan, guard, and baseline tests" \
  "$STAGE_DIR/focused.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --no-cov \
      tests/structure/test_caption_anchors.py \
      tests/structure/test_figure_regions.py \
      tests/structure/test_scan_pdf.py \
      tests/structure/test_table_page_guard.py \
      tests/structure/test_plan030_red_baselines.py

GOLD_LOG="$STAGE_DIR/gold.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  env PYTHONPATH="$ROOT/scripts:$ROOT" "$PY" - >"$GOLD_LOG" 2>&1 <<'PY'
from pathlib import Path

from qyunslation.structure.scan_pdf import PdfStructureScanner
from scripts.doc_image_prescan import format_tier3_summary, scan_pdf_tier3

root = Path("tests/fixtures/structure/reference")
ljae = root / "ljae439.pdf"
nature = root / "nature_comm_53384.pdf"

ljae_m = PdfStructureScanner().scan(ljae)
nature_m = PdfStructureScanner().scan(nature)
assert ljae_m.summary.figure_count == 5, ljae_m.summary.figure_count
assert ljae_m.summary.table_count == 3, ljae_m.summary.table_count
assert nature_m.summary.figure_count == 7, nature_m.summary.figure_count
assert nature_m.summary.table_count == 3, nature_m.summary.table_count

ljae_t3 = scan_pdf_tier3(ljae)
nature_t3 = scan_pdf_tier3(nature)
assert ljae_t3.figure_caption_count == 5, ljae_t3
assert ljae_t3.table_caption_count == 3, ljae_t3
assert nature_t3.figure_caption_count == 7, nature_t3
assert nature_t3.table_caption_count == 3, nature_t3
assert nature_t3.translatable_count == 7, nature_t3

text = format_tier3_summary(
    {},
    vector_count=ljae_t3.vector_count,
    table_count=ljae_t3.table_count,
    figure_caption_count=ljae_t3.figure_caption_count,
    table_caption_count=ljae_t3.table_caption_count,
    translatable_count=ljae_t3.translatable_count,
)
assert "5 张插图" in text
assert "3 处表格" in text
assert "7 处插图" not in text
assert "位图" not in text
print("gold_ok", ljae_t3.figure_caption_count, nature_t3.figure_caption_count)
PY
then
  pass "ljae439 and Nature semantic gold samples"
else
  fail "ljae439 and Nature semantic gold samples"
  show_failure_log "$GOLD_LOG"
fi

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
    "test_pptx_picture_shape_is_emitted_as_a_translatable_object",
}, xfails
assert not root.findall(".//failure")
assert not root.findall(".//error")
PY
  then
    expected_red "only PLAN-030g PPT image execution remains XFAIL"
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
  fail "--runxfail unexpectedly passed; the PLAN-030g PPT gap is stale"
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
    "test_pptx_picture_shape_is_emitted_as_a_translatable_object",
}, failed
assert not root.findall(".//error")
assert not root.findall(".//skipped")
PY
  then
    expected_red "--runxfail proves the exact PLAN-030g PPT gap still fails"
  else
    fail "--runxfail differs from the exact one-failure baseline"
    show_failure_log "$RUNXFAIL_LOG"
  fi
fi

run_pass \
  "full pytest regression excluding recorded archive failures" \
  "$STAGE_DIR/full.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov

ARCHIVE_XML="$STAGE_DIR/archive.xml"
ARCHIVE_LOG="$STAGE_DIR/archive.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/test_pdf2zh_archive.py --no-cov \
    --junitxml="$ARCHIVE_XML" >"$ARCHIVE_LOG" 2>&1; then
  fail "archive baseline changed unexpectedly; review it before updating the gate"
  show_failure_log "$ARCHIVE_LOG"
else
  if "$PY" - "$ARCHIVE_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

expected = {
    "test_output_group_key",
    "test_infer_original_filename",
    "test_ingest_pdf2zh_group_local",
}
root = ET.parse(Path(sys.argv[1])).getroot()
cases = root.findall(".//testcase")
failed = {case.attrib["name"] for case in cases if case.find("failure") is not None}
assert len(cases) == 3, len(cases)
assert failed == expected, (failed, expected)
assert not root.findall(".//error")
assert not root.findall(".//skipped")
PY
  then
    expected_red "three unchanged pre-PLAN-030 archive naming failures"
  else
    fail "archive regression differs from the recorded pre-PLAN-030 baseline"
    show_failure_log "$ARCHIVE_LOG"
  fi
fi

if [[ "$FAILURES" -eq 0 && "$BLOCKERS" -eq 0 && "$EXPECTED_REDS" -eq 3 ]]; then
  printf 'SUMMARY: PASS expected_red=%d blocked=0 fail=0\n' "$EXPECTED_REDS"
  exit 0
fi

printf 'SUMMARY: FAIL expected_red=%d blocked=%d fail=%d\n' \
  "$EXPECTED_REDS" "$BLOCKERS" "$FAILURES"
exit 1
