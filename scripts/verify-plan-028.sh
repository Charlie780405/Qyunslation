#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-028 预扫描口径对齐验收
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
SAMPLE="/home/dev/pdf2zh/pdf2zh_files/ef8f3e1f-fc80-4c84-bfca-bc2e9ac8d302/41467_2024_Article_53384.pdf"
PY="${PY:-/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python}"
FAIL=0

check() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  ok    %s\n' "$desc"
  else
    printf '  FAIL  %s\n' "$desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "== 1. 内核 API =="
grep -q 'def table_rects' "$SCRIPTS/pdf_figure_crop.py" && check "table_rects public" true || check "table_rects public" false
grep -q 'tables: list | None = None' "$SCRIPTS/pdf_figure_crop.py" && check "tables= param" true || check "tables= param" false
grep -q 'def scan_pdf_tier3' "$SCRIPTS/doc_image_prescan.py" && check "scan_pdf_tier3" true || check "scan_pdf_tier3" false
grep -q 'def format_tier3_summary' "$SCRIPTS/doc_image_prescan.py" && check "format_tier3_summary" true || check "format_tier3_summary" false

echo "== 2. 论文 PDF 结构扫描 =="
if [[ -f "$SAMPLE" ]]; then
  PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys, time
from pathlib import Path
sys.path.insert(0, "$SCRIPTS")
from doc_image_prescan import scan_pdf_tier3
from pdf_figure_crop import find_safe_vector_figures, table_rects
import pymupdf

p = Path("$SAMPLE")
t0 = time.time()
r = scan_pdf_tier3(p)
dt = time.time() - t0
assert r.vector_count == 12, f"vector_count={r.vector_count}"
assert r.table_count >= 19, f"table_count={r.table_count}"
assert dt < 15.0, f"tier3 slow {dt:.2f}s"
assert not r.error, r.error

doc = pymupdf.open(p)
page = doc[2]
tb = table_rects(page)
a = find_safe_vector_figures(page, tables=tb)
b = find_safe_vector_figures(page)
assert len(a) == len(b), f"tables= mismatch {len(a)} vs {len(b)}"
doc.close()
print("tier3_ok", r.vector_count, r.table_count, f"{dt:.2f}s")
PY
  check "tier3 sample pdf" test $? -eq 0
else
  printf '  skip  sample pdf missing\n'
fi

echo "== 3. GUI 补丁 =="
check "tier3 helper" grep -q 'def _qy_prescan_tier3(' "$GUI"
check "tier3 wired" grep -q '_qy_prescan_tier3,' "$GUI"
check "vector_count in gui" grep -q 'vector_count' "$GUI"
check "gui syntax" "$PY" -m py_compile "$GUI"

echo "== 4. 幂等 =="
check "prescan idempotent" sh -c "python3 '$SCRIPTS/apply-pdf2zh-prescan.py' 2>&1 | grep -q 'already patched'"

if [[ "$FAIL" -eq 0 ]]; then
  echo "PASS ($FAIL failures)"
else
  echo "FAIL ($FAIL failures)"
fi
exit "$FAIL"
