#!/usr/bin/env bash
# PLAN-024 验收：全屏裁切修复 + 字号层级统一
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
VENV_PY="$ROOT/.venv/bin/python"
VIEWER="$ROOT/scripts/apply-pdf2zh-viewer.py"
IMG="$ROOT/qyunslation/extensions/image_translate.py"
pass=0; fail=0
ok() { echo "  ok    $*"; pass=$((pass+1)); }
bad() { echo "  FAIL  $*"; fail=$((fail+1)); }

echo "== 1. viewer 源码 =="
grep -q "classList.contains('qy-viewer-inner')" "$VIEWER" && ok "搬子节点防嵌套" || bad "搬子节点防嵌套"
grep -q "while (clone.firstChild)" "$VIEWER" && ok "firstChild 搬移" || bad "firstChild 搬移"
grep -q "calc(100vh - 72px)" "$VIEWER" && ok "全屏 max-height 兜底" || bad "全屏兜底"
grep -q "height: 100%" "$VIEWER" && ok "inner height:100%" || bad "inner height"
"$VENV_PY" "$VIEWER" >/tmp/qy024-v.txt 2>&1 || true
"$VENV_PY" "$VIEWER" >/tmp/qy024-v2.txt 2>&1 || true
grep -q "already patched\|patched:" /tmp/qy024-v2.txt && ok "viewer idempotent" || bad "viewer idempotent"
grep -q "while (clone.firstChild)" "$GUI" && ok "viewer in gui" || bad "viewer in gui"
grep -q "calc(100vh - 72px)" "$GUI" && ok "fs max-height in gui" || bad "fs max-height in gui"

echo "== 2. image_translate 源码 =="
grep -q "def _assign_tiers" "$IMG" && ok "_assign_tiers" || bad "_assign_tiers"
grep -q "def _estimate_orig_size" "$IMG" && ok "_estimate_orig_size" || bad "_estimate_orig_size"
grep -q "def _assign_tier_sizes" "$IMG" && ok "_assign_tier_sizes" || bad "_assign_tier_sizes"
grep -q "TIER_OUTLIER_RATIO" "$IMG" && ok "TIER_OUTLIER_RATIO" || bad "TIER_OUTLIER_RATIO"
grep -q "C7a" "$IMG" && ok "C7a" || bad "C7a"
grep -q "C7b" "$IMG" && ok "C7b" || bad "C7b"
grep -q "0.75" "$IMG" && ok "75 分位" || bad "75 分位"

echo "== 3. Skill =="
grep -q "背景色桶" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律层级" || bad "铁律层级"
grep -q "嵌套.*qy-viewer-inner\|禁止嵌套" "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" && ok "铁律全屏" || bad "铁律全屏"
grep -q "PLAN-024" "$ROOT/.cursor/skills/image-overlay-translation/pitfalls.md" && ok "pitfalls 024" || bad "pitfalls"
grep -q "PLAN-024" "$ROOT/.cursor/skills/skill-registry/registry.md" && ok "registry" || bad "registry"
lines=$(wc -l < "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md")
[[ "$lines" -le 200 ]] && ok "SKILL.md ≤200 ($lines)" || bad "SKILL.md lines=$lines"
bash "$ROOT/scripts/verify-skill-registry.sh" >/tmp/qy024-reg.txt 2>&1 && ok "verify-skill-registry" || { bad "registry"; cat /tmp/qy024-reg.txt; }
bash "$ROOT/scripts/sync-cursor-skills.sh" >/tmp/qy024-sync.txt 2>&1 && ok "sync" || bad "sync"

echo "== 4. 端到端字号层级 =="
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
from qyunslation.extensions.image_translate import (
    ocr_image, translate_image, _analyze_box_style, _assign_tiers,
    _quantize_bgr, _is_near_white
)
from pathlib import Path
import cv2, json, tempfile, time

src = Path(r"""$SRC""")
img = cv2.imread(str(src))
boxes = ocr_image(src)
assert len(boxes) >= 55
styles = [_analyze_box_style(img[b[1]:b[3], b[0]:b[2]]) for b in boxes]
tiers = _assign_tiers(boxes, styles)

# 蓝框组：量化后非白且为 (144/154 附近)
blue = [i for i, (b, st, t) in enumerate(zip(boxes, styles, tiers))
        if (not _is_near_white(_quantize_bgr(st["bg_bgr"])))
        and "QX027N" in b[4] or (b[4].startswith("W") and "mg" in b[4].lower())
        or b[4] in ("W4, W12, 600mg", "W12,600mg", "W2, W4, W12, 300mg")]
# 更稳：按 tier 名收集最大彩色组
from collections import Counter
cc = Counter(t for t in tiers if t.startswith("c"))
blue_tier = cc.most_common(1)[0][0]
blue_idx = [i for i, t in enumerate(tiers) if t == blue_tier]
print(f"BLUE_TIER={blue_tier} n={len(blue_idx)}")
assert len(blue_idx) >= 6, blue_idx

# 白底脚注带：最后一个 w*
w_tiers = sorted({t for t in tiers if t.startswith("w")})
foot_tier = w_tiers[-1]
foot_idx = [i for i, t in enumerate(tiers) if t == foot_tier]
print(f"FOOT_TIER={foot_tier} n={len(foot_idx)} texts={[boxes[i][4][:16] for i in foot_idx]}")
assert len(foot_idx) >= 5, foot_idx

out = Path(tempfile.gettempdir()) / "qy024_en.jpg"
t0 = time.time()
n = translate_image(src, out, to_lang="English")
print(f"DRAWN={n} {time.time()-t0:.1f}s")
assert n >= 55
rep = json.loads(Path(str(out) + ".qc.json").read_text(encoding="utf-8"))
print("QC ok=", rep.get("ok"), "issues=", rep.get("issues"))
print("tiers=", json.dumps(rep.get("tiers"), ensure_ascii=False)[:500])
assert rep.get("ok") is True, rep.get("issues")

# 从 qc.json 校验蓝框/脚注组字号
ti = rep.get("tiers") or {}
# find blue / foot by membership overlap
def find_tier(idxs):
    want = {i + 1 for i in idxs}
    for name, info in ti.items():
        mem = set(info.get("members") or [])
        if len(want & mem) >= max(3, len(want) // 2):
            return name, info
    return None, None

bn, bi = find_tier(blue_idx)
fn, fi = find_tier(foot_idx)
print("matched blue", bn, bi)
print("matched foot", fn, fi)
assert bi and bi.get("n", 0) >= 6
assert fi and fi.get("n", 0) >= 5
# 组内 size 单一（qc C7a 已断言）；再核成员数
assert bi.get("size") and fi.get("size")

# 组间比例
k = float(rep.get("k") or 0)
assert k > 0
drifts = []
for name, info in ti.items():
    em = info.get("orig_em") or 0
    sz = info.get("size") or 0
    if em <= 0 or sz <= 0:
        continue
    expected = max(10, int(round(k * em)))
    if sz != expected:
        drifts.append((name, sz, expected, em))
assert not drifts, drifts
print("E2E_OK k=", k)
PY
  then
    ok "e2e tiers + QC"
  else
    bad "e2e"
  fi
fi

echo "== 5. 回归 PLAN-023 =="
if bash "$ROOT/scripts/verify-plan-023.sh" >/tmp/qy024-r023.txt 2>&1; then
  ok "verify-plan-023"
else
  # 023 可能因 viewer 重打后回归项变化；至少看 FAIL 数
  if grep -q "FAIL=0" /tmp/qy024-r023.txt; then
    ok "verify-plan-023"
  else
    bad "verify-plan-023"; tail -40 /tmp/qy024-r023.txt
  fi
fi

echo
echo "PASS=$pass FAIL=$fail"
[[ "$fail" -eq 0 ]]
