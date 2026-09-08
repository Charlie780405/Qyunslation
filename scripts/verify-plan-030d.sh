#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030d PDF vertical closure: manifest SSOT, body/columns, table protection,
# and native/scanned/hybrid parity.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
# 结构套件已增长到 500s 量级，短超时会把 SIGINT 当成测试失败上报
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
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

# 不影响判定，只交代加强回归为何没跑
info() {
  printf 'INFO: %s\n' "$1"
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

# PLAN-030h H1：仓外样本只作加强回归。默认根是 pdf2zh 的运行时会话目录，
# 会被回收，缺失不得阻断主门——主门断言走仓内合成等价夹具。
SAMPLE_ROOT="${QYUNSLATION_SAMPLE_ROOT:-/home/dev/pdf2zh/pdf2zh_files}"
MISSING_SAMPLES=0
for rel in \
  "57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf" \
  "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.pdf" \
  "5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.hpd-ocr.pdf"
do
  if [[ ! -f "$SAMPLE_ROOT/$rel" ]]; then
    info "strengthened regression skipped, sample absent: $SAMPLE_ROOT/$rel"
    MISSING_SAMPLES=$((MISSING_SAMPLES + 1))
  fi
done
if [[ "$MISSING_SAMPLES" -eq 0 ]]; then
  pass "external gold samples present under QYUNSLATION_SAMPLE_ROOT"
else
  pass "main gate runs on in-repo synthetic equivalents ($MISSING_SAMPLES strengthened skipped)"
fi

run_pass \
  "PLAN-030d modules compile" \
  "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure \
    scripts/doc_image_prescan.py \
    scripts/pdf_figure_crop.py \
    scripts/pdf_image_translate.py

run_pass \
  "manifest SSOT, body/columns, table protection, scanned parity tests" \
  "$STAGE_DIR/focused.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
    "$PY" -m pytest -q --no-cov \
      tests/structure/test_manifest_store.py \
      tests/structure/test_prescan_manifest.py \
      tests/structure/test_execution_parity.py \
      tests/structure/test_prescan_error_surface.py \
      tests/structure/test_unnumbered_objects.py \
      tests/structure/test_column_layout.py \
      tests/structure/test_table_protection.py \
      tests/structure/test_scanned_pdf_parity.py

GOLD_LOG="$STAGE_DIR/gold.log"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  env PYTHONPATH="$ROOT/scripts:$ROOT" "$PY" - >"$GOLD_LOG" 2>&1 <<'PY'
from pathlib import Path

from qyunslation.structure.models import LayoutMode, ObjectType, ProcessingMode
from qyunslation.structure.scan_pdf import PdfStructureScanner

root = Path("tests/fixtures/structure/reference")
ljae = PdfStructureScanner().scan(root / "ljae439.pdf")
nature = PdfStructureScanner().scan(root / "nature_comm_53384.pdf")

# 030c 的语义计数不得因 030d 的正文/表格改动而漂移
assert ljae.summary.figure_count == 5, ljae.summary.figure_count
assert ljae.summary.table_count == 3, ljae.summary.table_count
assert nature.summary.figure_count == 7, nature.summary.figure_count
assert nature.summary.table_count == 3, nature.summary.table_count
assert ljae.extensions["translatable_figure_count"] == 6
assert nature.extensions["translatable_figure_count"] == 7

# Task 6-7：正文对象、栏式与阅读顺序
for manifest, name in ((ljae, "ljae439"), (nature, "nature")):
    bodies = [o for o in manifest.objects if o.type is ObjectType.BODY]
    assert bodies, f"{name} produced no BODY objects"
    assert all(b.planned_action == "babeldoc_text_layer" for b in bodies)
    for canvas in manifest.canvases:
        orders = [b.reading_order for b in bodies if b.canvas_id == canvas.canvas_id]
        assert orders == list(range(len(orders))), (name, canvas.canvas_id)

modes = [c.layout_mode for c in nature.canvases]
assert LayoutMode.MIXED not in modes, "layout_mode is still the hardcoded placeholder"
assert sum(1 for m in modes if m is LayoutMode.DOUBLE) == 18, modes
assert sum(1 for m in [c.layout_mode for c in ljae.canvases] if m is LayoutMode.SINGLE) == 2

# 双栏页阅读顺序必须左栏在前
bodies = {o.object_id: o for o in nature.objects if o.type is ObjectType.BODY}
for canvas in nature.canvases:
    if canvas.layout_mode is not LayoutMode.DOUBLE:
        continue
    columns = [
        bodies[oid].detector_evidence[0].details["column"]
        for oid in canvas.reading_order
    ]
    lefts = [i for i, c in enumerate(columns) if c == "left"]
    rights = [i for i, c in enumerate(columns) if c == "right"]
    if lefts and rights:
        assert max(lefts) < min(rights), canvas.canvas_id

# Task 8：六个表格区域全部圈定，无 geometry-missing 残留
for manifest in (ljae, nature):
    assert "TABLE_GEOMETRY_MISSING" not in {i.code for i in manifest.issues}
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert len(tables) == 3
    for table in tables:
        evidence = next(
            e for e in table.detector_evidence if e.detector == "table_rule_lines"
        )
        assert evidence.details["reconstructed"] is False
        assert table.planned_action == "text_layer"

# 表内文字不得漏进正文
p5 = [o for o in nature.objects if o.type is ObjectType.BODY and o.canvas_id == "page:5"]
assert len(p5) < 10, len(p5)

# Task 9：原生件判定与形态记录
assert ljae.extensions["document_representation"] == "NATIVE_TEXT"
assert ljae.extensions["needs_ocr"] is False
assert ljae.document.selected_mode is ProcessingMode.NATIVE
assert len(ljae.extensions["page_representations"]) == 10

print("gold_ok", ljae.summary.figure_count, nature.summary.figure_count)
PY
then
  pass "ljae439 and Nature body, column, table, and representation gold samples"
else
  fail "ljae439 and Nature body, column, table, and representation gold samples"
  show_failure_log "$GOLD_LOG"
fi

SCANNED_LOG="$STAGE_DIR/scanned.log"
# 主门跑仓内合成等价件；仓外真实件（PIND）存在时同一组断言再跑一遍作加强。
PIND="$SAMPLE_ROOT/5fa54bcf-4843-4e97-8cd0-85c797fa9b5d/FDA responses on PIND.pdf"
if timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  env PYTHONPATH="$ROOT/scripts:$ROOT" QYUNSLATION_PIND="$PIND" \
  QYUNSLATION_FIXTURE_OUT="$STAGE_DIR/fixtures" \
  "$PY" - >"$SCANNED_LOG" 2>&1 <<'PY'
import importlib.util
import os
import time
from pathlib import Path

from qyunslation.structure.models import ExecutionStatus, ProcessingMode
from qyunslation.structure.scan_pdf import PdfStructureScanner

spec = importlib.util.spec_from_file_location(
    "plan030_fixtures", "tests/fixtures/structure/generate_synthetic.py"
)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

out = Path(os.environ["QYUNSLATION_FIXTURE_OUT"])
generator.generate_all(out)
expected_pages = generator.SCANNED_EQUIVALENT_PAGES


def assert_scanned(path: Path, label: str) -> None:
    started = time.monotonic()
    manifest = PdfStructureScanner().scan(path)
    elapsed = time.monotonic() - started

    assert manifest.extensions["document_representation"] == "SCANNED", label
    assert manifest.extensions["needs_ocr"] is True, label
    assert manifest.document.selected_mode is ProcessingMode.HYBRID, label
    ocr_issues = [i for i in manifest.issues if i.code == "PAGES_REQUIRE_OCR"]
    assert ocr_issues, label
    assert ocr_issues[0].details["pages"] == list(range(1, expected_pages + 1)), label
    assert not [
        o for o in manifest.objects if o.execution_status is ExecutionStatus.PENDING
    ], label
    # Tier-3 预算 25s；首版量图片覆盖的写法在真实 20 页扫描件上要 17.5s
    assert elapsed < 10.0, (label, elapsed)
    print(f"scanned_ok {label} {elapsed:.2f}")


assert_scanned(out / "scanned-equivalent.pdf", "synthetic")

pind = Path(os.environ["QYUNSLATION_PIND"])
if pind.is_file():
    assert_scanned(pind, "external-pind")
else:
    print(f"strengthened skipped, sample absent: {pind}")
PY
then
  pass "scanned-document prescan budget and OCR inventory"
else
  fail "scanned-document prescan budget and OCR inventory"
  show_failure_log "$SCANNED_LOG"
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

for gate in 028 029 030c; do
  GATE_LOG="$STAGE_DIR/gate-$gate.log"
  if QYUNSLATION_VERIFY_TIMEOUT_SECONDS="$TEST_TIMEOUT_SECONDS" \
    bash "scripts/verify-plan-$gate.sh" >"$GATE_LOG" 2>&1; then
    pass "PLAN-$gate gate still passes"
  else
    fail "PLAN-$gate gate regressed"
    show_failure_log "$GATE_LOG"
  fi
done

if [[ "$FAILURES" -eq 0 && "$BLOCKERS" -eq 0 && "$EXPECTED_REDS" -eq 1 ]]; then
  printf 'SUMMARY: PASS expected_red=%d blocked=0 fail=0\n' "$EXPECTED_REDS"
  exit 0
fi

printf 'SUMMARY: FAIL expected_red=%d blocked=%d fail=%d\n' \
  "$EXPECTED_REDS" "$BLOCKERS" "$FAILURES"
exit 1
