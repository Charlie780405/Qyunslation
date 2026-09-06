#!/usr/bin/env bash
# PLAN-023 验收：按通道纯色 / 一次 inpaint / 可用区 / getmetrics / QC
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
VENV_PY="$ROOT/.venv/bin/python"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

IMG="$ROOT/qyunslation/extensions/image_translate.py"
APP="$ROOT/qyunslation/app.py"

echo "== 1. 源码断言 =="
grep -q "SOLID_FRAC_MIN" "$IMG" && ok "SOLID_FRAC_MIN" || bad "SOLID_FRAC_MIN"
grep -q "inliers" "$IMG" && ok "内点 std" || bad "内点 std"
grep -q "float(np.std(border.astype" "$IMG" && bad "残留拍平 std" || ok "无拍平 std"
grep -q "def _available_box" "$IMG" && ok "_available_box" || bad "_available_box"
grep -q "def _qc_report" "$IMG" && ok "_qc_report" || bad "_qc_report"
grep -q "def _line_height" "$IMG" && ok "_line_height" || bad "_line_height"
grep -q "getmetrics" "$IMG" && ok "getmetrics" || bad "getmetrics"
grep -q "inpaint_mask" "$IMG" && ok "累加 inpaint_mask" || bad "inpaint_mask"
grep -q "def _erase_text_local" "$IMG" && ok "_erase_text_local" || bad "_erase_text_local"
# 循环内不应再有多次 cv2.inpaint（应只有一次）
inpaint_n=$(grep -c "cv2.inpaint" "$IMG" || true)
[[ "$inpaint_n" -eq 1 ]] && ok "inpaint 仅 1 处" || bad "inpaint 次数=$inpaint_n"
grep -q "kept_rois" "$IMG" && ok "未译框回贴" || bad "未译框回贴"
grep -q "border_bgr" "$IMG" && ok "border_bgr" || bad "border_bgr"
grep -q "min(int(box_h \* 0.9), 72)" "$IMG" && ok "max_size≤72" || bad "max_size"
grep -q "QYUNSLATION_IMAGE_QC_STRICT\|QC_STRICT" "$IMG" && ok "QC_STRICT" || bad "QC_STRICT"
grep -q "basicConfig" "$APP" && ok "app basicConfig" || bad "app basicConfig"
grep -q "Path(font_bold).is_file" "$IMG" && ok "font_bold is_file" || bad "font_bold guard"
grep -q "pad = 2 if min" "$IMG" && ok "边框内缩采样" || bad "边框内缩采样"

echo "== 2. Skill =="
test -f "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "SKILL.md" || bad "SKILL.md"
grep -q "按通道" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律按通道" || bad "铁律按通道"
grep -q "QC 六项\|_qc_report" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律 QC" || bad "铁律 QC"
grep -q "BGR 拍平\|_16周\|getbbox 墨迹" "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls PLAN-023" || bad "pitfalls"
grep -q "PLAN-023" "$ROOT/.cursor/skills/skill-registry/registry.md" && ok "registry 审计" || bad "registry"
lines=$(wc -l < "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md")
[[ "$lines" -le 200 ]] && ok "SKILL.md ≤200 ($lines)" || bad "SKILL.md lines=$lines"
bash "$ROOT/scripts/verify-skill-registry.sh" >/tmp/qy023-reg.txt 2>&1 && ok "verify-skill-registry" || { bad "registry"; cat /tmp/qy023-reg.txt; }
bash "$ROOT/scripts/sync-cursor-skills.sh" >/tmp/qy023-sync.txt 2>&1 && ok "sync-cursor-skills" || bad "sync"

echo "== 3. 端到端（中译英 + solid + QC） =="
SRC=""
for c in /tmp/gradio/*/方案设计图-20260728.jpg /tmp/qyunslation_*/方案设计图-20260728.jpg; do
  if [[ -f "$c" && ! "$c" =~ \.zh\. ]]; then SRC="$c"; break; fi
done
if [[ -z "$SRC" ]]; then
  bad "test image missing"
else
  while IFS= read -r line; do
    case "$line" in
      ''|\#*) continue ;;
      DOCUTRANSLATE_BASE_URL=*|DOCUTRANSLATE_MODEL_ID=*|QYUNSLATION_*=*)
        export "${line%%=*}=${line#*=}"
        ;;
    esac
  done < /home/dev/pdf2zh/office.env
  export PYTHONPATH="$ROOT"
  export QYUNSLATION_IMAGE_QC_STRICT=0
  if "$VENV_PY" - <<PY
from qyunslation.extensions.image_translate import (
    ocr_image, translate_image, _analyze_box_style, CONTRAST_MIN
)
from pathlib import Path
import cv2, json, time, tempfile

src = Path(r"""$SRC""")
img = cv2.imread(str(src))
boxes = ocr_image(src)
print(f"OCR_BOXES={len(boxes)}")
assert len(boxes) >= 55

solid_n = 0
min_c = 999.0
for b in boxes:
    st = _analyze_box_style(img[b[1]:b[3], b[0]:b[2]])
    solid_n += int(bool(st["solid"]))
    min_c = min(min_c, float(st["contrast"]))
print(f"SOLID={solid_n}/{len(boxes)} MIN_CONTRAST={min_c:.1f}")
assert solid_n >= 55, f"solid {solid_n} < 55"
assert min_c >= CONTRAST_MIN - 1e-6

out = Path(tempfile.gettempdir()) / "qy023_en.jpg"
t0 = time.time()
n = translate_image(src, out, to_lang="English")
print(f"DRAWN_EN={n} {time.time()-t0:.1f}s")
assert n >= 55
qc = Path(str(out) + ".qc.json")
assert qc.is_file(), "missing qc.json"
report = json.loads(qc.read_text(encoding="utf-8"))
print("QC_EN", json.dumps(report, ensure_ascii=False)[:400])
assert report.get("ok") is True, report.get("issues")
assert report.get("solid_count", 0) >= 55

# 英译中：把英译稿再翻回中文（二次 OCR 可能框数不同，只要求能跑通+有 QC）
out_zh = Path(tempfile.gettempdir()) / "qy023_zh.jpg"
t1 = time.time()
n2 = translate_image(out, out_zh, to_lang="简体中文")
print(f"DRAWN_ZH={n2} {time.time()-t1:.1f}s")
assert n2 >= 40
qc2 = Path(str(out_zh) + ".qc.json")
assert qc2.is_file()
report2 = json.loads(qc2.read_text(encoding="utf-8"))
print("QC_ZH ok=", report2.get("ok"), "issues=", report2.get("issues"))
# 二次 OCR 可能切碎英文，C1 未必全绿；硬要求无 C3 空白
hard = [x for x in report2.get("issues", []) if x.get("code") in ("C2", "C3", "C4")]
assert not hard, hard
print("E2E_OK")
PY
  then
    ok "e2e zh→en→zh + QC"
  else
    bad "e2e"
  fi
fi

echo "== 4. 回归 PLAN-017..022 =="
# 重打尾部补丁，避免 020 verify 剥掉 viewer
for p in apply-pdf2zh-layout-polish.py apply-pdf2zh-adv-options.py \
         apply-pdf2zh-left-dock.py apply-pdf2zh-glossary-encoding.py \
         apply-pdf2zh-no-store.py apply-pdf2zh-stale-guard.py \
         apply-pdf2zh-preview-url.py apply-pdf2zh-css-has-fix.py \
         apply-pdf2zh-viewer.py; do
  if [[ -f "$ROOT/scripts/$p" ]]; then
    "$VENV_PY" "$ROOT/scripts/$p" >/tmp/qy023-$p.txt 2>&1 || true
  fi
done
for v in verify-plan-022.sh; do
  if bash "$ROOT/scripts/$v" >/tmp/qy023-$v.txt 2>&1; then
    ok "$v"
  else
    bad "$v"; tail -40 /tmp/qy023-$v.txt
  fi
done

echo
echo "PASS=$pass FAIL=$fail"
[[ "$fail" -eq 0 ]]
