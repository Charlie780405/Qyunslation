#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030e DOCX vertical closure + gap remediation gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
SAMPLE_ROOT="${QYUNSLATION_SAMPLE_ROOT:-/home/dev/pdf2zh/pdf2zh_files}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKERS=0
EXPECTED_REDS=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT

cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKERS=$((BLOCKERS + 1)); }
expected_red() { printf 'EXPECTED_RED: %s\n' "$1"; EXPECTED_REDS=$((EXPECTED_REDS + 1)); }

show_failure_log() {
  [[ -f "$1" ]] && tail -n 60 "$1"
}

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; show_failure_log "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  blocked "Python runtime is unavailable at $PY"
  printf 'SUMMARY: FAIL expected_red=0 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

if ! command -v soffice >/dev/null 2>&1 && ! command -v libreoffice >/dev/null 2>&1; then
  blocked "LibreOffice/soffice missing — run scripts/install-libreoffice.sh"
else
  pass "LibreOffice available"
fi

# PLAN-030h H1：仓外样本只作加强回归，缺失不阻断主门（主门走仓内合成等价夹具）
MISSING_SAMPLES=0
for rel in \
  "57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf" \
  "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.pdf" \
  "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.hpd-ocr.pdf"
do
  if [[ ! -f "$SAMPLE_ROOT/$rel" ]]; then
    printf 'INFO: strengthened regression skipped, sample absent: %s/%s\n' "$SAMPLE_ROOT" "$rel"
    MISSING_SAMPLES=$((MISSING_SAMPLES + 1))
  fi
done
if [[ "$MISSING_SAMPLES" -eq 0 ]]; then
  pass "external gold samples present"
else
  pass "main gate runs on in-repo synthetic equivalents ($MISSING_SAMPLES strengthened skipped)"
fi

run_pass "PLAN-030e modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q qyunslation/structure qyunslation/workflow/docx_workflow.py

run_pass "DOCX scan + contract schema" "$STAGE_DIR/docx.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov \
    tests/structure/test_scan_docx.py \
    tests/structure/test_manifest_contract.py::test_committed_json_schema_matches_model

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

for gate in 028 029 030c 030d; do
  GATE_LOG="$STAGE_DIR/gate-$gate.log"
  if QYUNSLATION_VERIFY_TIMEOUT_SECONDS="$TEST_TIMEOUT_SECONDS" \
    QYUNSLATION_SAMPLE_ROOT="$SAMPLE_ROOT" \
    bash "scripts/verify-plan-$gate.sh" >"$GATE_LOG" 2>&1; then
    pass "PLAN-$gate gate still passes"
  else
    fail "PLAN-$gate gate regressed"
    show_failure_log "$GATE_LOG"
  fi
done

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS expected_red=%d blocked=%d fail=0\n' "$EXPECTED_REDS" "$BLOCKERS"
  exit 0
fi
printf 'SUMMARY: FAIL expected_red=%d blocked=%d fail=%d\n' "$EXPECTED_REDS" "$BLOCKERS" "$FAILURES"
exit 1
