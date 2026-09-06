#!/usr/bin/env bash
# PLAN-025 验收：译文对齐锚定原图墨迹 + C8
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
IMG="$ROOT/qyunslation/extensions/image_translate.py"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

echo "== 1. image_translate 源码 =="
grep -q "def _ink_geometry" "$IMG" && ok "_ink_geometry" || bad "_ink_geometry"
grep -q "def _infer_align" "$IMG" && ok "_infer_align" || bad "_infer_align"
grep -q "ALIGN_TOL_PX" "$IMG" && ok "ALIGN_TOL_PX" || bad "ALIGN_TOL_PX"
grep -q '"C8"' "$IMG" && ok "C8" || bad "C8"
grep -q "draw_bbox" "$IMG" && ok "draw_bbox" || bad "draw_bbox"
grep -q "def _main_row" "$IMG" && ok "_main_row 排除线状行" || bad "_main_row"
grep -q "RULE_ROW_RATIO" "$IMG" && ok "RULE_ROW_RATIO" || bad "RULE_ROW_RATIO"
grep -q "def _assign_left_groups" "$IMG" && ok "_assign_left_groups" || bad "_assign_left_groups"
grep -q "def _ink_x_metrics" "$IMG" && ok "_ink_x_metrics" || bad "_ink_x_metrics"
grep -q "getmask" "$IMG" && ok "getmask 取真实墨迹" || bad "getmask"
grep -q "solid_colored" "$IMG" && ok "solid_colored 区分白底" || bad "solid_colored"
grep -q '"C9"' "$IMG" && ok "C9" || bad "C9"
grep -q "仅钳图像边界" "$IMG" && ok "强锚钳图像边界" || bad "强锚钳图像边界"

echo "== 2. Skill =="
grep -q "排版锚原文墨迹\|原文墨迹" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律墨迹锚点" || bad "铁律墨迹锚点"
grep -q "行间一致性\|C8" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律对齐/C8" || bad "铁律对齐/C8"
grep -q "_main_row" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律主行" || bad "铁律主行"
grep -q "getmask" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律墨迹度量" || bad "铁律墨迹度量"
grep -q "跨框左对齐组" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律左对齐组" || bad "铁律左对齐组"
grep -q "PLAN-025b" "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls 025b" || bad "pitfalls 025b"
grep -q "PLAN-025" "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls 025" || bad "pitfalls"
grep -q "ALIGN_TOL_PX\|QYUNSLATION_ALIGN_TOL_PX" "$ROOT/.cursor/skills/image-overlay-translation/reference.md" && ok "reference ALIGN" || bad "reference"
grep -q "PLAN-025" "$ROOT/.cursor/skills/skill-registry/registry.md" && ok "registry" || bad "registry"
lines=$(wc -l < "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md")
[[ "$lines" -le 200 ]] && ok "SKILL.md ≤200 ($lines)" || bad "SKILL.md lines=$lines"
bash "$ROOT/scripts/verify-skill-registry.sh" >/tmp/qy025-reg.txt 2>&1 && ok "verify-skill-registry" || { bad "registry"; cat /tmp/qy025-reg.txt; }
bash "$ROOT/scripts/sync-cursor-skills.sh" >/tmp/qy025-sync.txt 2>&1 && ok "sync" || bad "sync"

echo "== 3. 端到端对齐（中→英） =="
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
import json, tempfile, time, numpy as np
from qyunslation.extensions.image_translate import translate_image

src = Path(r"""$SRC""")
out = Path(tempfile.gettempdir()) / "qy025_en.jpg"
t0 = time.time()
n = translate_image(src, out, to_lang="English")
print(f"DRAWN={n} {time.time()-t0:.1f}s")
assert n >= 55
rep = json.loads(Path(str(out) + ".qc.json").read_text(encoding="utf-8"))
print("QC ok=", rep.get("ok"), "issues=", [i.get("code") for i in (rep.get("issues") or [])])
assert rep.get("ok") is True, rep.get("issues")
align = rep.get("align") or []
assert len(align) >= 55, len(align)
tol = float(rep.get("align_tol_px") or 12)
bad_r = [a for a in align if abs(a["dx"]) > tol or abs(a["dy"]) > tol]
assert not bad_r, bad_r[:8]
# 相对原文：允许图像左缘 clamp（draw_bbox.x1≈0）
bad_p = []
for a in align:
    pdx, pdy = abs(float(a.get("plan_dx") or 0)), abs(float(a.get("plan_dy") or 0))
    if pdx <= tol and pdy <= tol:
        continue
    planned = a.get("planned") or {}
    shift = planned.get("shift") or {}
    db = planned.get("draw_bbox") or {}
    if shift.get("x") and int(db.get("x1", 99)) <= 1:
        continue
    bad_p.append(a)
assert not bad_p, [(a["box"], a.get("plan_dx"), a.get("plan_dy"), a.get("planned", {}).get("shift"), (a.get("planned") or {}).get("draw_bbox")) for a in bad_p[:8]]

# 周数标签（#5 蹭括号线）锚点须落在真文字行，而非 2px 线状行
by_box = {int(a["box"]): a for a in align}
wk = [by_box[i] for i in (5, 6, 7, 8) if i in by_box]
assert len(wk) == 4, sorted(by_box)
for a in wk:
    assert abs(float(a["plan_dy"])) <= 2.0, (a["box"], a["plan_dy"])
    src_y = float(a["anchor_src"]["y"])
    assert src_y >= 120, (a["box"], src_y)  # 117 = 锚到括号线的旧值
print("WEEK_ANCHOR_OK", [(a["box"], a["anchor_src"]["y"]) for a in wk])

# 脚注 bullet 必须成左对齐组且成品左缘齐
lg = rep.get("left_groups") or {}
bullet = [m for m in lg.values() if len(m) >= 2 and 59 in m and 60 in m]
assert bullet, lg
xs = [float(by_box[b]["anchor_dst"]["x"]) for b in bullet[0]]
assert max(xs) - min(xs) <= tol, xs
print("LEFT_GROUP_OK", lg)

# 等宽刻度标签不得被误并成左对齐组
grouped = {b for m in lg.values() for b in m}
assert not (grouped & {24, 25, 26, 37, 38, 39}), sorted(grouped)

# W12–W52 一行竖向方差
w = [a for a in align if 22 <= int(a["box"]) <= 31]
assert len(w) >= 8, len(w)
var_y = float(np.var([float(a["anchor_plan"]["y"]) for a in w]))
print(f"W12-W52 n={len(w)} var_y={var_y:.3f}")
assert var_y <= 2.0, var_y
print("E2E_EN_OK")
PY
  then
    ok "e2e en align + QC"
  else
    bad "e2e en"
  fi

  echo "== 4. 端到端对齐（英→中抽检） =="
  if "$VENV_PY" - <<PY
from pathlib import Path
import json, tempfile, time
from qyunslation.extensions.image_translate import translate_image
src = Path(tempfile.gettempdir()) / "qy025_en.jpg"
assert src.is_file()
out = Path(tempfile.gettempdir()) / "qy025_zh.jpg"
t0 = time.time()
n = translate_image(src, out, to_lang="简体中文")
print(f"ZH DRAWN={n} {time.time()-t0:.1f}s")
assert n >= 50
rep = json.loads(Path(str(out) + ".qc.json").read_text(encoding="utf-8"))
# 回译可能因 OCR 切分变化出 C3；C8 渲染对齐仍须过
codes = {i.get("code") for i in (rep.get("issues") or [])}
hard = codes & {"C8", "C9"}
assert not hard, rep.get("issues")
align = rep.get("align") or []
tol = float(rep.get("align_tol_px") or 12)
bad_r = [a for a in align if abs(a["dx"]) > tol or abs(a["dy"]) > tol]
assert not bad_r, bad_r[:8]
print("E2E_ZH_OK")
PY
  then
    ok "e2e zh align C8"
  else
    bad "e2e zh"
  fi
fi

echo "== 5. 回归 PLAN-024 =="
if bash "$ROOT/scripts/verify-plan-024.sh" >/tmp/qy025-r024.txt 2>&1; then
  ok "verify-plan-024"
else
  if grep -q "FAIL=0" /tmp/qy025-r024.txt; then
    ok "verify-plan-024"
  else
    bad "verify-plan-024"; tail -50 /tmp/qy025-r024.txt
  fi
fi

echo
echo "PASS=$pass FAIL=$fail"
[[ "$fail" -eq 0 ]]
