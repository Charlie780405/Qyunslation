#!/usr/bin/env bash
# PLAN-026 验收：擦除保护（文字带填充 + 线保护）与竖向三段式锚定 + C10
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
IMG="$ROOT/qyunslation/extensions/image_translate.py"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

echo "== 1. image_translate 源码 =="
grep -q "def _fill_band" "$IMG" && ok "_fill_band" || bad "_fill_band"
grep -q "def _line_guard_mask" "$IMG" && ok "_line_guard_mask" || bad "_line_guard_mask"
grep -q "def _text_rows\|_def _is_rule_row" "$IMG" && ok "线状行辅助" || bad "线状行辅助"
grep -q "FILL_BAND_PAD\|QYUNSLATION_FILL_BAND_PAD" "$IMG" && ok "FILL_BAND_PAD" || bad "FILL_BAND_PAD"
grep -q "GRAPHICS_DAMAGE_MAX" "$IMG" && ok "GRAPHICS_DAMAGE_MAX" || bad "GRAPHICS_DAMAGE_MAX"
grep -q "vertical_mode" "$IMG" && ok "vertical_mode" || bad "vertical_mode"
grep -q '"C10"' "$IMG" && ok "C10" || bad "C10"
grep -q "文字带外整段回贴" "$IMG" && ok "文字带外回贴" || bad "文字带外回贴"
grep -q '"C1", "C2", "C3", "C4", "C8", "C9", "C10"' "$IMG" && ok "QC_STRICT 含 C10" || bad "QC_STRICT C10"

echo "== 2. Skill =="
grep -q "通用原则\|OCR 框不是文字范围" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "通用原则" || bad "通用原则"
grep -q "_fill_band\|文字带" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律文字带填充" || bad "铁律文字带"
grep -q "竖向三段式\|能放下就保中心" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律竖向三段" || bad "铁律竖向"
grep -q "新图\|接入自检\|自检清单" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "新图自检清单" || bad "自检清单"
grep -q "C10" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "SKILL C10" || bad "SKILL C10"
grep -q "PLAN-026" "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls 026" || bad "pitfalls 026"
grep -q "GRAPHICS_DAMAGE_MAX\|FILL_BAND_PAD\|竖向三段" "$ROOT/.cursor/skills/image-overlay-translation/reference.md" && ok "reference 026" || bad "reference 026"
grep -q "PLAN-026" "$ROOT/.cursor/skills/skill-registry/registry.md" && ok "registry" || bad "registry"
lines=$(wc -l < "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md")
[[ "$lines" -le 220 ]] && ok "SKILL.md ≤220 ($lines)" || bad "SKILL.md lines=$lines"
bash "$ROOT/scripts/verify-skill-registry.sh" >/tmp/qy026-reg.txt 2>&1 && ok "verify-skill-registry" || { bad "registry"; cat /tmp/qy026-reg.txt; }
bash "$ROOT/scripts/sync-cursor-skills.sh" >/tmp/qy026-sync.txt 2>&1 && ok "sync" || bad "sync"

echo "== 3. 端到端（中→英）：括号线 + 周数居中 + C10 =="
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
  export PYTHONPATH="$ROOT" QYUNSLATION_IMAGE_QC_STRICT=0
  if "$VENV_PY" - <<PY
from pathlib import Path
import json, tempfile, time, cv2, numpy as np
from qyunslation.extensions.image_translate import translate_image

src = Path(r"""$SRC""")
out = Path(tempfile.gettempdir()) / "qy026_en.jpg"
t0 = time.time()
n = translate_image(src, out, to_lang="English")
print(f"DRAWN={n} {time.time()-t0:.1f}s")
assert n >= 55
rep = json.loads(Path(str(out) + ".qc.json").read_text(encoding="utf-8"))
print("QC ok=", rep.get("ok"), "issues=", [i.get("code") for i in (rep.get("issues") or [])])
hard = {i.get("code") for i in (rep.get("issues") or [])} & {"C8", "C9", "C10"}
assert not hard, rep.get("issues")
assert not (rep.get("graphics_damage") or []), rep.get("graphics_damage")

# 括号线存活：y=116-117, x=3160..3320
o = cv2.imread(str(src))
e = cv2.imread(str(out))
band_o = o[116:118, 3160:3320]
band_e = e[116:118, 3160:3320]
nw_o = int((band_o.astype(int).sum(2) < 720).sum())
nw_e = int((band_e.astype(int).sum(2) < 720).sum())
ratio = nw_e / max(1, nw_o)
print(f"BRACKET_SURVIVAL orig={nw_o} en={nw_e} ratio={ratio:.3f}")
assert ratio >= 0.90, (nw_o, nw_e, ratio)

# 周数标签 #5/#6/#7/#8：原文 ink_cy 与 draw_bbox cy 差 ≤3
al = {int(a["box"]): a for a in (rep.get("align") or [])}
for bi in (5, 6, 7, 8):
    a = al[bi]
    ink = a["planned"]["ink_src"]
    db = a["planned"]["draw_bbox"]
    ocy = (ink["y1"] + ink["y2"]) / 2.0
    dcy = (db["y1"] + db["y2"]) / 2.0
    assert abs(ocy - dcy) <= 3.0, (bi, ocy, dcy, a.get("vertical_mode"))
    assert a.get("vertical_mode") == "center" or a["planned"].get("vertical_mode") == "center", a
print("WEEK_CENTER_OK", [(bi, al[bi]["planned"].get("vertical_mode")) for bi in (5, 6, 7, 8)])
print("E2E_EN_OK")
PY
  then ok "e2e en bracket+center+C10"
  else bad "e2e en"
  fi

  echo "== 4. 端到端（英→中抽检） =="
  if "$VENV_PY" - <<PY
from pathlib import Path
import json, tempfile
from qyunslation.extensions.image_translate import translate_image
src = Path(tempfile.gettempdir()) / "qy026_en.jpg"
out = Path(tempfile.gettempdir()) / "qy026_zh.jpg"
n = translate_image(src, out, to_lang="简体中文")
print(f"ZH DRAWN={n}")
assert n >= 55
rep = json.loads(Path(str(out) + ".qc.json").read_text(encoding="utf-8"))
hard = {i.get("code") for i in (rep.get("issues") or [])} & {"C8", "C9", "C10"}
assert not hard, rep.get("issues")
print("E2E_ZH_OK")
PY
  then ok "e2e zh C8/C9/C10"
  else bad "e2e zh"
  fi
fi

echo "== 5. 回归 PLAN-025 =="
if bash "$ROOT/scripts/verify-plan-025.sh" >/tmp/qy026-reg025.txt 2>&1; then
  ok "verify-plan-025"
else
  bad "verify-plan-025"
  tail -40 /tmp/qy026-reg025.txt
fi

echo "PASS=$pass FAIL=$fail"
[[ "$fail" -eq 0 ]]
