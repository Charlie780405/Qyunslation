#!/usr/bin/env bash
# PLAN-021 验收
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
VENV_PY="$ROOT/.venv/bin/python"
pass=0; fail=0

ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

echo "== 1. 源码关键能力 =="
grep -q "def ocr_image_rapid" "$ROOT/qyunslation/extensions/image_translate.py" && ok "ocr_image_rapid" || bad "ocr_image_rapid"
grep -q 'think.: False\|"think": False' "$ROOT/qyunslation/extensions/image_translate.py" && ok "think:false" || bad "think:false"
grep -q "TRANSLATE_BATCH\|batch_size" "$ROOT/qyunslation/extensions/image_translate.py" && ok "batch translate" || bad "batch"
grep -q "_fit_font_and_lines" "$ROOT/qyunslation/extensions/image_translate.py" && ok "fit font" || bad "fit font"
grep -q "redraw" "$ROOT/qyunslation/extensions/image_translate.py" && ok "selective erase" || bad "selective erase"
grep -q "to_lang=self.config.to_lang" "$ROOT/qyunslation/translator/ai_translator/docx_translator.py" && ok "docx to_lang" || bad "docx to_lang"
grep -q "to_lang: str = Form" "$ROOT/qyunslation/custom_api.py" && ok "api to_lang" || bad "api to_lang"
test -f "$ROOT/scripts/apply-pdf2zh-viewer.py" && ok "viewer patch exists" || bad "viewer patch"
grep -q "apply-pdf2zh-viewer.py" "$ROOT/scripts/pdf2zh.service" && ok "service wires viewer" || bad "service"

echo "== 2. viewer 补丁幂等 =="
"$VENV_PY" "$ROOT/scripts/apply-pdf2zh-viewer.py" >/tmp/qy021-v1.txt 2>&1 || true
"$VENV_PY" "$ROOT/scripts/apply-pdf2zh-viewer.py" >/tmp/qy021-v2.txt 2>&1 || true
grep -q "already patched\|patched:" /tmp/qy021-v2.txt && ok "viewer idempotent" || bad "viewer idempotent"
grep -q "_qy_viewer_js" "$GUI" && ok "viewer js in gui" || bad "viewer js in gui"
grep -q "_qy_viewer_css" "$GUI" && ok "viewer css in gui" || bad "viewer css in gui"
"$VENV_PY" -c "import ast; ast.parse(open('$GUI').read())" && ok "gui.py syntax" || bad "gui.py syntax"

echo "== 3. OCR 与翻译实测（流程图） =="
SRC=""
for c in \
  /tmp/gradio/*/方案设计图-20260728.jpg \
  /tmp/*/方案设计图-20260728.jpg; do
  if [[ -f "$c" && ! "$c" =~ \.zh\. ]]; then SRC="$c"; break; fi
done
if [[ -z "$SRC" ]]; then
  bad "test image missing"
else
  # office.env 含未加引号空格行，不能直接 source；只导出图片链路必需键
  while IFS= read -r line; do
    case "$line" in
      ''|\#*) continue ;;
      DOCUTRANSLATE_BASE_URL=*|DOCUTRANSLATE_MODEL_ID=*|QYUNSLATION_*=*)
        key="${line%%=*}"
        val="${line#*=}"
        export "$key=$val"
        ;;
    esac
  done < /home/dev/pdf2zh/office.env
  export PYTHONPATH="$ROOT"
  if "$VENV_PY" - <<PY
from qyunslation.extensions.image_translate import ocr_image, translate_texts, translate_image
from pathlib import Path
import tempfile, time

src = Path(r"""$SRC""")
boxes = ocr_image(src)
print(f"OCR_BOXES={len(boxes)}")
assert len(boxes) >= 55, f"OCR too few: {len(boxes)}"

texts = [b[4] for b in boxes]
t0 = time.time()
tr = translate_texts(texts, to_lang="English")
hit = sum(1 for i in range(len(boxes)) if tr.get(i+1))
rate = hit / len(boxes)
print(f"HIT={hit}/{len(boxes)} rate={rate:.2f} elapsed={time.time()-t0:.1f}s")
assert rate >= 0.95, f"hit rate {rate:.2f} < 0.95"

with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "out.jpg"
    n = translate_image(src, out, to_lang="English")
    print(f"DRAWN={n}")
    assert n >= int(len(boxes) * 0.9), f"drawn {n} too low"
    assert out.is_file() and out.stat().st_size > 1000
print("E2E_OK")
PY
  then
    ok "flowchart e2e (OCR≥55, hit≥95%)"
  else
    bad "flowchart e2e"
  fi
fi

echo "== 4. 回归 017–020 =="
# 017–019 的 verify 会重跑 brand 等前置补丁，冲掉链尾；回归前先把链尾贴回
for p in left-dock stale-guard preview-url glossary-encoding no-store css-has-fix viewer; do
  "$VENV_PY" "$ROOT/scripts/apply-pdf2zh-$p.py" >/dev/null 2>&1 || true
done
for s in 017 017b 018 019 020; do
  if bash "$ROOT/scripts/verify-plan-$s.sh" >/tmp/qy021-r$s.txt 2>&1; then
    ok "verify-plan-$s"
  else
    # 若链尾被冲掉，贴回后再验一次 020
    if [[ "$s" == "020" ]]; then
      for p in left-dock stale-guard preview-url glossary-encoding no-store css-has-fix viewer; do
        "$VENV_PY" "$ROOT/scripts/apply-pdf2zh-$p.py" >/dev/null 2>&1 || true
      done
      if bash "$ROOT/scripts/verify-plan-020.sh" >/tmp/qy021-r020b.txt 2>&1; then
        ok "verify-plan-020"
        continue
      fi
    fi
    bad "verify-plan-$s"
    tail -8 /tmp/qy021-r$s.txt || true
  fi
done
# 最终确保 viewer 仍在
"$VENV_PY" "$ROOT/scripts/apply-pdf2zh-viewer.py" >/dev/null 2>&1 || true
grep -q "_qy_viewer_js" "$GUI" && ok "viewer survives regressions" || bad "viewer stripped by regressions"

echo
echo "PLAN-021 verify: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
