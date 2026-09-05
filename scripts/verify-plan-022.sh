#!/usr/bin/env bash
# PLAN-022 验收：配色/纯色填充/粗体对齐/viewer/Skill
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
VENV_PY="$ROOT/.venv/bin/python"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

IMG="$ROOT/qyunslation/extensions/image_translate.py"

echo "== 1. 源码 =="
grep -q "def _analyze_box_style" "$IMG" && ok "_analyze_box_style" || bad "_analyze_box_style"
grep -q "vals < 120" "$IMG" && bad "残留 vals<120" || ok "无 vals<120"
grep -q "FONT_BOLD\|_font_bold" "$IMG" && ok "FONT_BOLD" || bad "FONT_BOLD"
grep -q 'st\["solid"\]\|st.get("solid"' "$IMG" && ok "solid fill branch" || bad "solid fill"
grep -q 'align' "$IMG" && ok "align" || bad "align"

echo "== 2. viewer =="
"$VENV_PY" "$ROOT/scripts/apply-pdf2zh-viewer.py" >/tmp/qy022-v.txt 2>&1 || true
"$VENV_PY" "$ROOT/scripts/apply-pdf2zh-viewer.py" >/tmp/qy022-v2.txt 2>&1 || true
grep -q "already patched\|patched:" /tmp/qy022-v2.txt && ok "viewer idempotent" || bad "viewer idempotent"
grep -q "querySelectorAll('img, canvas" "$ROOT/scripts/apply-pdf2zh-viewer.py" && bad "旧嵌套选择器残留" || ok "无嵌套双命中选择器"
grep -q "cloneNode(true)" "$ROOT/scripts/apply-pdf2zh-viewer.py" && ok "整容器克隆" || bad "整容器克隆"
grep -q "_qy_viewer_js" "$GUI" && ok "viewer in gui" || bad "viewer in gui"

echo "== 3. Skill registry =="
test -f "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "SKILL.md" || bad "SKILL.md"
test -f "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls.md" || bad "pitfalls.md"
test -f "$ROOT/.cursor/skills/image-overlay-translation/reference.md" && ok "reference.md" || bad "reference.md"
grep -q "SK-Q002" "$ROOT/.cursor/skills/skill-registry/registry.md" && ok "registry SK-Q002" || bad "registry"
lines=$(wc -l < "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md")
[[ "$lines" -le 200 ]] && ok "SKILL.md ≤200 ($lines)" || bad "SKILL.md lines=$lines"
if bash "$ROOT/scripts/verify-skill-registry.sh" >/tmp/qy022-reg.txt 2>&1; then
  ok "verify-skill-registry"
else
  bad "verify-skill-registry"; cat /tmp/qy022-reg.txt
fi
bash "$ROOT/scripts/sync-cursor-skills.sh" >/tmp/qy022-sync.txt 2>&1 && ok "sync-cursor-skills" || bad "sync"

echo "== 4. 流程图端到端（对比度） =="
SRC=""
for c in /tmp/gradio/*/方案设计图-20260728.jpg; do
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
  if "$VENV_PY" - <<PY
from qyunslation.extensions.image_translate import (
    ocr_image, translate_texts, translate_image, _analyze_box_style, CONTRAST_MIN
)
from pathlib import Path
import cv2, tempfile, time

src = Path(r"""$SRC""")
img = cv2.imread(str(src))
boxes = ocr_image(src)
print(f"OCR_BOXES={len(boxes)}")
assert len(boxes) >= 55

# 取色对比度（原图）
contrasts = []
for b in boxes:
    st = _analyze_box_style(img[b[1]:b[3], b[0]:b[2]])
    contrasts.append(st["contrast"])
min_c = min(contrasts) if contrasts else 0
print(f"STYLE_MIN_CONTRAST={min_c:.1f} (threshold {CONTRAST_MIN})")
assert min_c >= CONTRAST_MIN - 1e-6, f"contrast {min_c} < {CONTRAST_MIN}"

texts = [b[4] for b in boxes]
tr = translate_texts(texts, to_lang="English")
hit = sum(1 for i in range(len(boxes)) if tr.get(i+1))
rate = hit / len(boxes)
print(f"HIT={hit}/{len(boxes)} rate={rate:.2f}")
assert rate >= 0.95

with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "out.jpg"
    t0 = time.time()
    n = translate_image(src, out, to_lang="English")
    print(f"DRAWN={n} elapsed={time.time()-t0:.1f}s")
    assert n >= int(len(boxes) * 0.9)
    assert out.is_file() and out.stat().st_size > 1000
print("E2E_OK")
PY
  then ok "flowchart contrast+translate"
  else bad "flowchart e2e"
  fi
fi

echo "== 5. 回归 =="
for p in left-dock stale-guard preview-url glossary-encoding no-store css-has-fix viewer; do
  "$VENV_PY" "$ROOT/scripts/apply-pdf2zh-$p.py" >/dev/null 2>&1 || true
done
for s in 017 017b 018 019 020 021; do
  if bash "$ROOT/scripts/verify-plan-$s.sh" >/tmp/qy022-r$s.txt 2>&1; then
    ok "verify-plan-$s"
  else
    if [[ "$s" == "020" || "$s" == "021" ]]; then
      for p in left-dock stale-guard preview-url glossary-encoding no-store css-has-fix viewer; do
        "$VENV_PY" "$ROOT/scripts/apply-pdf2zh-$p.py" >/dev/null 2>&1 || true
      done
      if bash "$ROOT/scripts/verify-plan-$s.sh" >/tmp/qy022-r${s}b.txt 2>&1; then
        ok "verify-plan-$s"; continue
      fi
    fi
    bad "verify-plan-$s"; tail -6 /tmp/qy022-r$s.txt || true
  fi
done

echo
echo "PLAN-022 verify: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
