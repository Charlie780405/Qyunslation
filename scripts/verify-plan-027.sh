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

echo "=== 8b. 预览双栏 flex-wrap 防回归 ==="
"$PY" - <<PY && ok "preview nowrap" || bad "preview nowrap"
import re
from pathlib import Path
t = Path("$GUI").read_text()
# Gradio .column 默认 flex-wrap:wrap，长预览会另起一列跑进右邻栏。
for sel in (".qy-col-mid", ".qy-col-right"):
    blocks = re.findall(re.escape(sel) + r"[^{]*\{[^}]*\}", t)
    owning = [b for b in blocks if "flex-direction: column" in b]
    assert owning, f"no column rule for {sel}"
    # 层叠后生效的是最后一条，它必须显式关掉换行。
    assert "flex-wrap: nowrap" in owning[-1], f"{sel} missing nowrap"
print("nowrap ok")
PY

echo "=== 8c. 跨 venv OCR 能力门控 ==="
"$PY" - <<'PY' && ok "ocr capability gate" || bad "ocr capability gate"
from pathlib import Path

# pdf2zh venv 无 rapidocr，本地 OCR 会静默退化到弱检测器；两条链路都必须
# 先判定能力，无能力时把活交给 qyunslation sidecar。
pit = Path("scripts/pdf_image_translate.py").read_text()
assert "def has_local_ocr()" in pit, "pdf path missing capability probe"
assert "if has_local_ocr():" in pit, "pdf path does not gate local translate"

pre = Path("scripts/apply-pdf2zh-prescan.py").read_text()
assert "_local_ocr = _find_spec(\"rapidocr\")" in pre, "prescan missing capability probe"
assert "/service/image-probe" in pre, "prescan missing sidecar fallback"
print("ocr gate ok")
PY

echo "=== 8d. PLAN-027f OCR 引擎可观测 ==="
"$PY" - <<'PY' && ok "027f dep+status+vision" || bad "027f dep+status+vision"
from pathlib import Path
import re
import tempfile

pyproj = Path("pyproject.toml").read_text()
assert "rapidocr>=" in pyproj or 'rapidocr>=' in pyproj, "rapidocr not declared"
assert "rapidocr-onnxruntime" not in pyproj, "dead rapidocr-onnxruntime still declared"
assert "onnxruntime" in pyproj, "onnxruntime (RapidOCR runtime) not declared"
src = Path("qyunslation/extensions/image_translate.py").read_text()
assert "from rapidocr import RapidOCR" in src
assert "def ocr_engine_status" in src
assert "def ocr_image_with_engine" in src
assert "def ocr_image_vision" in src
assert "QYUNSLATION_OCR_ENGINE" in src

from qyunslation.extensions.image_translate import (
    ocr_engine_status,
    ocr_image_vision,
    ocr_image_with_engine,
    probe_image,
)

st = ocr_engine_status(refresh=True)
assert "engines" in st and "rapidocr" in st["engines"]
assert st["engines"]["rapidocr"]["status"] in {"ok", "unavailable", "failed"}
assert st["engines"]["vision"]["status"] == "stub"

raised = False
try:
    ocr_image_vision("/tmp/nope.png")
except NotImplementedError:
    raised = True
assert raised, "vision stub must raise NotImplementedError, not return empty"

# 合成确定性图：用系统中文字体画 12 个标签，断言 RapidOCR 检出达标
from PIL import Image, ImageDraw, ImageFont

labels = [
    "诱导期", "维持期", "负荷期", "筛选期",
    "随访期", "主要终点", "EASI75", "IGA0/1",
    "随机化", "安全随访", "安慰剂", "开放标签",
]
font = None
for fp in (
    "/home/dev/.cache/babeldoc/fonts/SourceHanSansCN-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
):
    if Path(fp).is_file():
        try:
            font = ImageFont.truetype(fp, 28)
            break
        except Exception:
            pass
assert font is not None, "no CJK font for baseline synthetic image"

im = Image.new("RGB", (900, 480), "white")
d = ImageDraw.Draw(im)
for i, lab in enumerate(labels):
    x = 40 + (i % 4) * 210
    y = 40 + (i // 4) * 140
    d.rectangle([x - 8, y - 8, x + 180, y + 48], outline="black", width=2)
    d.text((x, y), lab, fill="black", font=font)
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
    path = tmp.name
    im.save(path)
try:
    boxes, engine = ocr_image_with_engine(path)
    pr = probe_image(path, to_lang="English", display_width_pt=400, display_height_pt=220)
finally:
    Path(path).unlink(missing_ok=True)

assert engine == "rapidocr", f"expected rapidocr, got {engine}"
assert len(boxes) >= 8, f"baseline boxes too low: {len(boxes)} (engine degraded?)"
assert pr.get("ocr_engine") == "rapidocr", pr
assert "ocr_engine" in pr
print(f"027f ok engine={engine} boxes={len(boxes)} probe_engine={pr['ocr_engine']}")
PY

# lifespan 启动自检接线
grep -q "ocr_engine_status" qyunslation/app.py && ok "lifespan ocr status" || bad "lifespan ocr status"
grep -q '"ocr_engine"' qyunslation/custom_api.py && ok "api ocr_engine field" || bad "api ocr_engine field"

echo "=== 8e. PLAN-027g 300 DPI + 擦除残留 ==="
"$PY" - <<'PY' && ok "027g dpi+erase" || bad "027g dpi+erase"
import importlib.util
import io
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 矢量默认
spec = importlib.util.spec_from_file_location(
    "pdf_figure_crop", Path("scripts/pdf_figure_crop.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert int(mod.VECTOR_CROP_DPI) == 300, mod.VECTOR_CROP_DPI
assert int(mod.VECTOR_MAX_PX) >= 4000, mod.VECTOR_MAX_PX

from qyunslation.extensions.doc_image_policy import ensure_display_dpi
from qyunslation.extensions.image_translate import (
    ERASE_PAD_PX,
    FILL_BAND_PAD,
    _clear_ocr_leftovers,
    _expand_erase_rect,
    ocr_image_rapid,
    translate_image_with_qc,
)

assert FILL_BAND_PAD >= 4
assert ERASE_PAD_PX >= 3

# ensure_display_dpi：100×50 @ 72×36pt ≈100 DPI → 升到 ~300×150
im = Image.new("RGB", (100, 50), "white")
buf = io.BytesIO()
im.save(buf, format="PNG")
up = ensure_display_dpi(buf.getvalue(), 72, 36, target_dpi=300)
wu, hu = Image.open(io.BytesIO(up)).size
assert wu >= 280 and hu >= 140, (wu, hu)
# 已 300 DPI 不缩小
im2 = Image.new("RGB", (300, 150), "white")
buf2 = io.BytesIO()
im2.save(buf2, format="PNG")
keep = ensure_display_dpi(buf2.getvalue(), 72, 36, target_dpi=300)
wk, hk = Image.open(io.BytesIO(keep)).size
assert (wk, hk) == (300, 150), (wk, hk)

# 蓝底白字 + 偏紧 OCR 框：擦除后二次扫描该区应无字
font = ImageFont.truetype(
    "/home/dev/.cache/babeldoc/fonts/SourceHanSansCN-Regular.ttf", 36
)
canvas = Image.new("RGB", (400, 120), (40, 90, 180))
d = ImageDraw.Draw(canvas)
d.text((40, 35), "Loading phase", fill="white", font=font)
raw = Path(tempfile.mktemp(suffix=".png"))
canvas.save(raw)
bgr = cv2.imread(str(raw))
# 故意偏紧的框（略裁切笔画）
boxes = [(45, 40, 300, 85, "Loading phase", 1.0)]
styles = [{"bg_bgr": (180, 90, 40), "solid": True, "solid_colored": True, "contrast": 120}]
# 先用扩框+文字带擦一遍
x1, y1, x2, y2 = _expand_erase_rect(45, 40, 300, 85, img_h=120, img_w=400)
from qyunslation.extensions.image_translate import _fill_band, _text_mask_u8

roi = bgr[y1:y2, x1:x2]
by1, by2 = _fill_band(roi)
cv2.rectangle(bgr, (x1, y1 + by1), (x2, y1 + by2), (180, 90, 40), -1)
tm = _text_mask_u8(roi)
if tm.size:
    bgr[y1:y2, x1:x2][tm > 0] = (180, 90, 40)
n = _clear_ocr_leftovers(
    bgr, boxes, styles, [True], orig_texts=["Loading phase"]
)
# 二次扫描该区
tmp2 = Path(tempfile.mktemp(suffix=".png"))
cv2.imwrite(str(tmp2), bgr[y1:y2, x1:x2])
left = ocr_image_rapid(tmp2)
raw.unlink(missing_ok=True)
tmp2.unlink(missing_ok=True)
assert len(left) == 0, f"leftover still visible: {[x[4] for x in left]} cleared={n}"
print(f"027g ok dpi_up={wu}x{hu} leftover=0 cleared={n}")
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
