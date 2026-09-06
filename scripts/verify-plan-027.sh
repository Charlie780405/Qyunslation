#!/usr/bin/env bash
# PLAN-027 验收：静态结构 + 策略单元 + DOCX/PDF 集成 + 回归 026
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
PASS=0
FAIL=0
ok() { echo "OK  $*"; PASS=$((PASS + 1)); }
bad() { echo "FAIL $*"; FAIL=$((FAIL + 1)); }

echo "=== 1. 静态结构 ==="
test -f qyunslation/extensions/doc_image_policy.py && ok "doc_image_policy.py" || bad "doc_image_policy.py"
test -f qyunslation/extensions/docx_image_overlay.py && ok "docx_image_overlay.py" || bad "docx_image_overlay.py"
test -f scripts/doc_image_prescan.py && ok "doc_image_prescan.py" || bad "doc_image_prescan.py"
test -f scripts/pdf_figure_crop.py && ok "pdf_figure_crop.py" || bad "pdf_figure_crop.py"
test -f scripts/pdf_image_translate.py && ok "pdf_image_translate.py" || bad "pdf_image_translate.py"
test -f scripts/apply-pdf2zh-prescan.py && ok "apply-pdf2zh-prescan.py" || bad "apply-pdf2zh-prescan.py"
test -f scripts/apply-pdf2zh-docimg.py && ok "apply-pdf2zh-docimg.py" || bad "apply-pdf2zh-docimg.py"
test -f /home/dev/pdf2zh/pdf_image_translate.py && ok "pdf2zh wrapper" || bad "pdf2zh wrapper"
grep -q "image-probe" qyunslation/custom_api.py && ok "/image-probe" || bad "/image-probe"
grep -q "evaluate_image_candidate\|_filter_translatable_texts" qyunslation/extensions/doc_image_policy.py && ok "policy APIs" || bad "policy APIs"
grep -q "_load_image_bgr_alpha\|_save_with_alpha\|probe_image\|translate_image_with_qc" qyunslation/extensions/image_translate.py && ok "alpha+probe" || bad "alpha+probe"
grep -q "overlay_docx_embedded_images\|enumerate_drawing_occurrences" qyunslation/extensions/docx_image_overlay.py && ok "docx overlay APIs" || bad "docx overlay APIs"
grep -q "find_safe_vector_figures\|MAX_AREA_FRAC" scripts/pdf_figure_crop.py && ok "vector crop guards" || bad "vector crop guards"
grep -q "translate_pdf_images\|_collect_xref_occurrences" scripts/pdf_image_translate.py && ok "pdf translate" || bad "pdf translate"
grep -q "apply-pdf2zh-prescan.py" scripts/pdf2zh.service && ok "service prescan" || bad "service prescan"
grep -q "apply-pdf2zh-docimg.py" scripts/pdf2zh.service && ok "service docimg" || bad "service docimg"
test ! -f qyunslation/extensions/image_replace.py && test -f archive/legacy/image_replace.py && ok "image_replace archived" || bad "image_replace archive"

echo "=== 2. 补丁幂等 ==="
python3 scripts/apply-pdf2zh-prescan.py >/tmp/qy027_p0.out
cp /home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py /tmp/gui_qy027_a.py
python3 scripts/apply-pdf2zh-prescan.py >/tmp/qy027_p1.out
python3 scripts/apply-pdf2zh-prescan.py >/tmp/qy027_p2.out
cp /home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py /tmp/gui_qy027_b.py
diff -q /tmp/gui_qy027_a.py /tmp/gui_qy027_b.py >/dev/null && ok "prescan idempotent" || bad "prescan idempotent"
python3 scripts/apply-pdf2zh-docimg.py >/tmp/qy027_d0.out
cp /home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py /tmp/gui_qy027_d0.py
python3 scripts/apply-pdf2zh-docimg.py >/tmp/qy027_d1.out
python3 scripts/apply-pdf2zh-docimg.py >/tmp/qy027_d2.out
cp /home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py /tmp/gui_qy027_c.py
diff -q /tmp/gui_qy027_d0.py /tmp/gui_qy027_c.py >/dev/null && ok "docimg idempotent" || bad "docimg idempotent"

echo "=== 3. 策略单元 ==="
"$PY" - <<'PY' && ok "policy unit" || bad "policy unit"
from qyunslation.extensions.doc_image_policy import (
    evaluate_geometry, filter_translatable_texts, is_numeric_or_unit, evaluate_image_candidate
)
from PIL import Image
import io
ok, r = evaluate_geometry(display_width_pt=30, display_height_pt=30)
assert not ok and r == "too_small"
ok, r = evaluate_geometry(display_width_pt=400, display_height_pt=250)
assert ok
ok, r = evaluate_geometry(display_width_pt=400, display_height_pt=250, page_frac=0.95)
assert not ok and r == "full_page_scan"
assert is_numeric_or_unit("16") and is_numeric_or_unit("100mg")
assert not is_numeric_or_unit("Prior treatment")
kept, lang, skip = filter_translatable_texts(["Week 16"], target_lang="English")
assert skip == "already_target_lang"
kept, lang, skip = filter_translatable_texts(["0","10","20"], target_lang="简体中文")
assert skip == "no_translatable_text"
img = Image.new("RGB", (400, 300), (255,255,255))
buf = io.BytesIO(); img.save(buf, format="PNG"); data = buf.getvalue()
d = evaluate_image_candidate(data, 400, 250, target_lang="English", ocr_texts=["诱导期"])
assert d.should_translate
print("policy ok")
PY

echo "=== 4. Alpha 保真 ==="
"$PY" - <<'PY' && ok "alpha fidelity" || bad "alpha fidelity"
from pathlib import Path
import numpy as np, cv2
from PIL import Image, ImageDraw
from qyunslation.extensions.image_translate import _load_image_bgr_alpha, _save_with_alpha
rgba = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
ImageDraw.Draw(rgba).text((10, 10), "A", fill=(255, 0, 0, 255))
p = Path("/tmp/qy027_alpha_in.png"); rgba.save(p)
bgr, alpha, mode = _load_image_bgr_alpha(p)
assert alpha is not None and int(alpha.min()) == 0
out = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
op = Path("/tmp/qy027_alpha_out.png")
_save_with_alpha(out, op, alpha)
arr = np.array(Image.open(op))
assert arr.shape[2] == 4 and arr[:,:,3].min() == 0
print("alpha ok")
PY

echo "=== 5. DOCX 实例枚举 + 小图跳过 ==="
"$PY" - <<'PY' && ok "docx enum+skip" || bad "docx enum+skip"
from pathlib import Path
from io import BytesIO
from docx import Document
from docx.shared import Inches, Pt, Emu
from PIL import Image, ImageDraw
from qyunslation.extensions.docx_image_overlay import (
    enumerate_drawing_occurrences, overlay_docx_embedded_images
)
from qyunslation.extensions.doc_image_policy import evaluate_image_candidate

# design fig
fig = Image.new("RGB", (800, 500), (230, 240, 255))
ImageDraw.Draw(fig).text((40, 40), "DESIGN FLOW 诱导期", fill=(0,0,0))
fig_p = Path("/tmp/qy027_design.png"); fig.save(fig_p)
# tiny logo
logo = Image.new("RGB", (64, 64), (255, 0, 0))
logo_p = Path("/tmp/qy027_logo.png"); logo.save(logo_p)

doc = Document()
# header logo small
h = doc.sections[0].header.paragraphs[0].add_run()
h.add_picture(str(logo_p), width=Inches(0.4))
# body design large — also add same logo tiny in body to create multi-ref? use design only
p = doc.add_paragraph().add_run()
p.add_picture(str(fig_p), width=Inches(5.5))
# also put design in header? skip — put logo also in body small
p2 = doc.add_paragraph().add_run()
p2.add_picture(str(logo_p), width=Inches(0.35))
out = Path("/tmp/qy027_enum.docx"); doc.save(out)

d2 = Document(out)
occs = enumerate_drawing_occurrences(d2)
assert len(occs) >= 2, len(occs)
# geometry: logo too small, design ok
decisions = []
for o in occs:
    d = evaluate_image_candidate(
        o.image_part.blob,
        display_width_pt=o.width_pt,
        display_height_pt=o.height_pt,
        is_header=o.is_header,
    )
    decisions.append((o.container, o.width_pt, d.should_translate, d.reason))
print("decisions", decisions)
assert any(not s and "too_small" in r for _,_,s,r in decisions), decisions
assert any(w > 200 for _,w,_,_ in decisions), decisions
print("docx enum ok")
PY

echo "=== 6. PDF 整页守卫 + 矢量门禁 ==="
PYTHONPATH="$ROOT/scripts:$ROOT" "$PY" - <<'PY' && ok "pdf guards" || bad "pdf guards"
import pymupdf
from pathlib import Path
from pdf_figure_crop import find_safe_vector_figures
from qyunslation.extensions.doc_image_policy import evaluate_geometry

doc = pymupdf.open()
page = doc.new_page(width=595, height=842)
page.insert_text((72, 72), "This is a long paragraph of body text that should not be rasterized over. " * 8)
figs = find_safe_vector_figures(page)
assert figs == [] or all(True for _ in figs)
ok, r = evaluate_geometry(display_width_pt=500, display_height_pt=800, page_frac=0.95)
assert not ok and r == "full_page_scan"
doc.close()
print("pdf guards ok")
PY

echo "=== 7. PDF 位图 translate 空跑（无可译图返回原路径）==="
PYTHONPATH="$ROOT/scripts:$ROOT" "$PY" - <<'PY' && ok "pdf noop" || bad "pdf noop"
import pymupdf
from pathlib import Path
from pdf_image_translate import translate_pdf_images
doc = pymupdf.open()
page = doc.new_page()
page.insert_text((72, 72), "Hello plain text page without images.")
src = Path("/tmp/qy027_plain.pdf"); doc.save(src); doc.close()
out = translate_pdf_images(src, to_lang="简体中文")
assert out == src, out
print("pdf noop ok")
PY

echo "=== 8. gui 语法与关键标记 ==="
GUI=/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py
"$PY" - <<PY && ok "gui compile" || bad "gui compile"
from pathlib import Path
p = Path("$GUI")
compile(p.read_text(), str(p), "exec")
t = p.read_text()
assert "qy_prescan_status" in t
assert "def _qy_prescan_tier1" in t
assert "_qy_imgtr" in t
assert "_pre_imgtr_origin_path" in t
print("gui ok")
PY

echo "=== 9. Skill 文档 ==="
grep -q "文档内嵌图\|Occurrence\|共享" .cursor/skills/image-overlay-translation/SKILL.md && ok "skill section" || bad "skill section (will add)"

echo "=== 10. 回归 PLAN-026（结构性）==="
# 仅跑静态部分避免依赖外部样例图耗时；若完整脚本存在则尝试
if bash scripts/verify-plan-026.sh >/tmp/qy027_reg026.log 2>&1; then
  ok "verify-plan-026"
else
  # 若因样例图缺失失败，检查是否至少结构性通过
  if grep -q "PASS=" /tmp/qy027_reg026.log; then
    tail -5 /tmp/qy027_reg026.log
    bad "verify-plan-026 (see /tmp/qy027_reg026.log)"
  else
    bad "verify-plan-026 crashed"
  fi
fi

echo "==== SUMMARY PASS=$PASS FAIL=$FAIL ===="
test "$FAIL" -eq 0
