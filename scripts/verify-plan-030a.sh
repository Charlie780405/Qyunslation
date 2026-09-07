#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030a contract, fixture, expected-red, and regression gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-300}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKERS=0

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
}

blocked() {
  printf 'BLOCKED: %s\n' "$1"
  BLOCKERS=$((BLOCKERS + 1))
}

show_failure_log() {
  local log_path="$1"
  if [[ -f "$log_path" ]]; then
    tail -n 40 "$log_path"
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
  printf 'SUMMARY: pass=0 expected_red=0 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

if [[ ! "$TEST_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  blocked "QYUNSLATION_VERIFY_TIMEOUT_SECONDS must be a positive integer"
  printf 'SUMMARY: pass=0 expected_red=0 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
  exit 1
fi

run_pass \
  "structure modules compile" \
  "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q qyunslation/structure tests/fixtures/structure/generate_synthetic.py

run_pass \
  "Manifest, format, profile, and fixture contracts" \
  "$STAGE_DIR/contracts.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q tests/structure \
    --ignore=tests/structure/test_plan030_red_baselines.py --no-cov

RED_XML="$STAGE_DIR/red.xml"
RED_LOG="$STAGE_DIR/red.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure/test_plan030_red_baselines.py \
  --no-cov --junitxml="$RED_XML" >"$RED_LOG" 2>&1; then
  if "$PY" - "$RED_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
cases = root.findall(".//testcase")
xfails = [
    case
    for case in cases
    if (node := case.find("skipped")) is not None
    and node.attrib.get("type") == "pytest.xfail"
]
assert len(cases) == 6, len(cases)
assert len(xfails) == 6, len(xfails)
assert not root.findall(".//failure")
assert not root.findall(".//error")
PY
  then
    expected_red "6 strict PLAN-030 gaps are XFAIL with no SKIP or XPASS"
  else
    fail "strict XFAIL inventory changed"
    show_failure_log "$RED_LOG"
  fi
else
  fail "strict XFAIL baseline does not pass in default pytest mode"
  show_failure_log "$RED_LOG"
fi

RUNXFAIL_XML="$STAGE_DIR/runxfail.xml"
RUNXFAIL_LOG="$STAGE_DIR/runxfail.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure/test_plan030_red_baselines.py \
  --runxfail --no-cov --junitxml="$RUNXFAIL_XML" >"$RUNXFAIL_LOG" 2>&1; then
  fail "--runxfail unexpectedly passed; at least one red baseline is stale"
  show_failure_log "$RUNXFAIL_LOG"
else
  if "$PY" - "$RUNXFAIL_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
cases = root.findall(".//testcase")
failures = root.findall(".//failure")
assert len(cases) == 6, len(cases)
assert len(failures) == 6, len(failures)
assert not root.findall(".//error")
assert not root.findall(".//skipped")
PY
  then
    expected_red "--runxfail proves all 6 documented gaps still fail"
  else
    fail "--runxfail result is not the exact 6-failure baseline"
    show_failure_log "$RUNXFAIL_LOG"
  fi
fi

KB_RESULT="$STAGE_DIR/kb-result.txt"
if "$PY" - "$ROOT" >"$KB_RESULT" 2>&1 <<'PY'
from pathlib import Path
import hashlib
import json
import os
import re
import sys

root = Path(sys.argv[1])
truth_path = root / "tests/fixtures/structure/ljae439.truth.json"
truth = json.loads(truth_path.read_text(encoding="utf-8"))
source = truth["source"]
assert truth["usage_scope"] == "TEST_FIXTURE_ONLY"
assert source["kind"] == "KNOWLEDGE_BASE"
assert source["runtime_dependency"] is False
assert source["locator"].startswith("knowledge-base://")

if source["import_state"] == "PENDING":
    assert source["sha256"] is None
    print("reserved knowledge-base fixture; byte import is deferred to PLAN-030b")
elif source["import_state"] == "IMPORTED":
    expected = source["sha256"]
    assert isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected)
    candidate = os.environ.get("QYUNSLATION_LJAE439_FIXTURE")
    if not candidate:
        print("IMPORTED metadata requires QYUNSLATION_LJAE439_FIXTURE for byte verification")
        raise SystemExit(3)
    path = Path(candidate)
    assert path.is_file(), path
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected, (actual, expected)
    print(f"verified imported knowledge-base fixture: {actual}")
else:
    raise AssertionError(source["import_state"])
PY
then
  pass "knowledge base is test-fixture-only and integrity policy is valid"
else
  kb_code=$?
  if [[ "$kb_code" -eq 3 ]]; then
    blocked "ljae439 is marked IMPORTED but its bytes were not supplied for verification"
  else
    fail "ljae439 fixture metadata is invalid"
  fi
  show_failure_log "$KB_RESULT"
fi

run_pass \
  "full pytest regression excluding three pre-existing archive failures" \
  "$STAGE_DIR/full.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --ignore=tests/test_pdf2zh_archive.py --no-cov

ARCHIVE_XML="$STAGE_DIR/archive.xml"
ARCHIVE_LOG="$STAGE_DIR/archive.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/test_pdf2zh_archive.py --no-cov \
  --junitxml="$ARCHIVE_XML" >"$ARCHIVE_LOG" 2>&1; then
  fail "pre-existing archive baseline changed unexpectedly; review before updating the gate"
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
    expected_red "3 unchanged pre-PLAN-030 archive naming failures"
  else
    fail "archive regression differs from the recorded pre-PLAN-030 baseline"
    show_failure_log "$ARCHIVE_LOG"
  fi
fi

if [[ "$FAILURES" -eq 0 && "$BLOCKERS" -eq 0 ]]; then
  printf 'SUMMARY: PASS expected_red=9 blocked=0 fail=0\n'
  exit 0
fi

printf 'SUMMARY: FAIL expected_red<=9 blocked=%d fail=%d\n' "$BLOCKERS" "$FAILURES"
exit 1
