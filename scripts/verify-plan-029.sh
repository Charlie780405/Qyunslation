#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-029 表格译文结构化验收
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
PY="${PY:-/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python}"
JOURNAL="/home/dev/pdf2zh/pdf2zh_files/ef8f3e1f-fc80-4c84-bfca-bc2e9ac8d302/41467_2024_Article_53384.pdf"
SLIDE="/home/dev/pdf2zh/pdf2zh_files/57114032-8727-41f9-b826-b5ff40fcf733/QX027N QnA-2026.08.19-临床.pdf"
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

echo "== 1. Hermes 跨仓 API =="
PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys
sys.path.insert(0, "/home/dev/Hermes/scripts")
from lit_tables import extract_tables_pdf, rows_to_markdown, trim_glued_rows, is_slide_page
assert all(callable(x) for x in (extract_tables_pdf, rows_to_markdown, trim_glued_rows, is_slide_page))
print("hermes_ok")
PY
check "lit_tables import" test $? -eq 0

echo "== 2. md_tables 内核 =="
check "md_tables module" test -f "$SCRIPTS/md_tables.py"
check "inject_translated_tables" grep -q 'def inject_translated_tables' "$SCRIPTS/md_tables.py"
check "pipe caption fallback" grep -q '_PIPE_CAPTION' "$SCRIPTS/md_tables.py"
check "md_tables syntax" "$PY" -m py_compile "$SCRIPTS/md_tables.py"

echo "== 3. 期刊 Markdown 注入 =="
if [[ -f "$JOURNAL" ]]; then
  PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys
from pathlib import Path
sys.path.insert(0, "$SCRIPTS")
sys.path.insert(0, "/home/dev/Hermes/scripts")
from lit_tables import extract_tables_pdf, trim_glued_rows
from md_tables import inject_translated_tables, _is_preserve_cell

p = Path("$JOURNAL")
tabs = extract_tables_pdf(p, use_hpd=False)
ok = [t for t in tabs if t.table_status == "ok"]
pending = [t for t in tabs if t.table_status == "pending"]
unstruct = [t for t in tabs if t.table_status == "unstructured"]
assert len(ok) >= 1, "need at least one ok table"
assert len(pending) >= 1, "need pending sample"
assert len(unstruct) >= 1, "need unstructured sample"
tab = ok[0]
rows = trim_glued_rows(tab.rows)
nums = [c for r in rows for c in r if _is_preserve_cell(str(c)) and str(c).strip()]
assert nums, "need numeric cells"
body = f"# Paper\\n\\n{tab.caption}\\n\\nTrailing prose.\\n"
out, stats = inject_translated_tables(body, p, translate_fn=lambda xs: [f"ZH_{x}" for x in xs])
assert stats["injected"] == 1, stats
assert stats["skipped_pending"] >= 1, stats
assert stats["skipped_unstructured"] >= 1, stats
assert "| --- |" in out, "missing markdown separator"
for n in nums[:15]:
    assert n in out, f"missing numeric {n!r}"
assert "ZH_" in out, "expected mock translation marker"
print("journal_inject_ok", stats)
PY
  check "journal inject + numeric preserve" test $? -eq 0
else
  printf '  skip  journal sample missing\n'
fi

echo "== 4. 幻灯 profile =="
check "slide constants" grep -q 'SLIDE_TEXT_OVERLAP' "$SCRIPTS/pdf_figure_crop.py"
check "is_slide_page" grep -q 'def is_slide_page' "$SCRIPTS/pdf_figure_crop.py"
check "profile params" grep -q 'text_overlap_max' "$SCRIPTS/pdf_figure_crop.py"
# PLAN-030c 补丁：幻灯分支收敛进 pdf_figure_crop.translatable_regions。
check "slide dispatch in figure_crop" grep -q 'def translatable_regions' "$SCRIPTS/pdf_figure_crop.py"
check "imgtr slide wiring" grep -q 'translatable_regions(page, exclude_rects=exclude)' "$SCRIPTS/pdf_image_translate.py"

if [[ -f "$SLIDE" ]]; then
  PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys
sys.path.insert(0, "$SCRIPTS")
import pymupdf
from pdf_figure_crop import (
    find_safe_vector_figures, is_slide_page,
    SLIDE_TEXT_OVERLAP, SLIDE_MAX_AREA_FRAC, SLIDE_MIN_DRAWINGS,
)

slide_path = "$SLIDE"
d = pymupdf.open(slide_path)
slide_pages = sum(is_slide_page(p) for p in d)
assert slide_pages == len(d), f"slide misdetect {slide_pages}/{len(d)}"

def count(fn):
    n = 0
    for p in d:
        n += len(fn(p))
    return n

baseline = count(lambda p: find_safe_vector_figures(p))
profile = count(lambda p: find_safe_vector_figures(
    p, tables=[], text_overlap_max=SLIDE_TEXT_OVERLAP,
    max_area_frac=SLIDE_MAX_AREA_FRAC, min_drawings=SLIDE_MIN_DRAWINGS,
))
d.close()
assert baseline == 8, f"baseline {baseline}"
assert profile >= 12, f"profile {profile}"
print("slide_profile_ok", baseline, profile)
PY
  check "slide profile 8->12" test $? -eq 0

  # PLAN-030c 补丁：幻灯无题注，预扫描必须与执行同口径（PLAN-027 不变量 4）。
  PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys
sys.path.insert(0, "$SCRIPTS")
import pymupdf
from doc_image_prescan import scan_pdf_tier3
from pdf_figure_crop import translatable_regions

d = pymupdf.open("$SLIDE")
execution = sum(len(translatable_regions(p)) for p in d)
d.close()
r = scan_pdf_tier3("$SLIDE")
assert execution == 12, f"slide execution {execution}"
assert r.translatable_count == execution, f"prescan {r.translatable_count} vs exec {execution}"
print("slide_parity_ok", r.translatable_count, execution)
PY
  check "slide prescan == execution" test $? -eq 0
else
  printf '  skip  slide sample missing\n'
fi

echo "== 5. PLAN-028 回归 =="
# PLAN-030c 口径变更：期刊用户口径改为题注可译区，不再断言几何矢量合计 12。
if [[ -f "$JOURNAL" ]]; then
  PYTHONPATH="$SCRIPTS:$ROOT" "$PY" - <<PY
import sys
sys.path.insert(0, "$SCRIPTS")
import pymupdf
from doc_image_prescan import scan_pdf_tier3
from pdf_figure_crop import find_safe_vector_figures

r = scan_pdf_tier3("$JOURNAL")
assert r.translatable_count == 7, f"journal translatable {r.translatable_count}"
d = pymupdf.open("$JOURNAL")
legacy = sum(len(find_safe_vector_figures(p)) for p in d)
d.close()
assert legacy == 12, f"legacy geometric regression {legacy}"
print("journal_ok", r.translatable_count, legacy)
PY
  check "journal translatable == 7" test $? -eq 0
fi

echo "== 6. export 挂载 =="
check "export inject hook" grep -q '_maybe_inject_tables' "$SCRIPTS/export_md_docx.py"
check "export debug path" grep -q 'export_from_debug' "$SCRIPTS/export_md_docx.py"
check "export hpd path inject" grep -A2 '_translate_markdown(en_md)' "$SCRIPTS/export_md_docx.py" | grep -q '_maybe_inject_tables'

if [[ "$FAIL" -eq 0 ]]; then
  echo "PASS ($FAIL failures)"
else
  echo "FAIL ($FAIL failures)"
fi
exit "$FAIL"
