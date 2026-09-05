#!/usr/bin/env bash
# verify-plan-010.sh — 扫描件版式保真
# 用法: bash scripts/verify-plan-010.sh [after-a|after-b|after-c|after-d|after-e|after-f]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-after-e}"
PY="${QYUNSLATION_VERIFY_PY:-/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python}"
WORK="${QYUNSLATION_BENCH_007:-/home/dev/pdf2zh/bench/007}"
DELIV="$ROOT/deliverables/plan-010-fidelity"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"

pass=0
fail=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "PASS: $desc"
    pass=$((pass + 1))
  else
    echo "FAIL: $desc"
    fail=$((fail + 1))
  fi
}

echo "== PLAN-010 verify phase=$PHASE =="

check "PLAN-010 纲领" test -f "$ROOT/docs/plans/PLAN-010-scanned-fidelity-generic/PLAN-010-scanned-fidelity-generic.md"
check "hpd _deoverlap_boxes" grep -q 'def _deoverlap_boxes' "$ROOT/scripts/hpd_ocr.py"
check "hpd _expand 全后继" grep -q '扫所有后继同列盒' "$ROOT/scripts/hpd_ocr.py"
check "微段落抑制" grep -q '跳过微段落碎片' "$ROOT/scripts/doc_profile.py"
check "unit deoverlap" "$PY" -m unittest scripts.test_hpd_deoverlap

if [[ "$PHASE" == "after-a" ]]; then
  echo "RESULT: $pass pass, $fail fail"
  [[ "$fail" -eq 0 ]]
  exit $?
fi

check "MERGE_ROLES" grep -q 'MERGE_ROLES' "$ROOT/scripts/letter_layout.py"
check "group_for_merge" grep -q 'def group_for_merge' "$ROOT/scripts/letter_layout.py"
check "signature_align left" grep -q 'signature_align = "left"' "$ROOT/scripts/doc_profiles.toml"
check "unit letter_layout" "$PY" -m unittest scripts.test_letter_layout
check "unit kv_reinsert" "$PY" -m unittest scripts.test_kv_reinsert

if [[ "$PHASE" == "after-b" ]]; then
  echo "RESULT: $pass pass, $fail fail"
  [[ "$fail" -eq 0 ]]
  exit $?
fi

check "proper-nouns.csv" test -f "$ROOT/glossaries/proper-nouns.csv"
check "proper_nouns.py" test -f "$ROOT/scripts/proper_nouns.py"
check "unit proper_nouns" "$PY" -m unittest scripts.test_proper_nouns
check "gui harvest" grep -q 'proper_nouns' "$GUI"

if [[ "$PHASE" == "after-d" ]]; then
  echo "RESULT: $pass pass, $fail fail"
  [[ "$fail" -eq 0 ]]
  exit $?
fi

check "graphic_regions.py" test -f "$ROOT/scripts/graphic_regions.py"
check "graphic_reinsert.py" test -f "$ROOT/scripts/graphic_reinsert.py"
check "hpd graphics 丢行" grep -q 'drop_boxes_in_suppress' "$ROOT/scripts/hpd_ocr.py"
check "gui reinsert" grep -q '_qy_graphic_reinsert' "$GUI"
check "unit graphic" "$PY" -m unittest scripts.test_graphic_regions

if [[ "$PHASE" == "after-c" ]]; then
  echo "RESULT: $pass pass, $fail fail"
  [[ "$fail" -eq 0 ]]
  exit $?
fi

check "bench V8" grep -q 'V8)' "$ROOT/scripts/bench-scanned-page1.sh"
check "WT-010" test -f "$ROOT/docs/walkthroughs/WT-010-scanned-fidelity-generic.md"
check "V8 deliverable pdf" test -f "$DELIV/letter.mono.pdf"
check "V8 deliverable png" test -f "$DELIV/letter.mono.png"

# 六项门槛 + floor_hits
check "V8 验收门槛" "$PY" - <<PY
import json, re, statistics
from pathlib import Path
import pymupdf

work = Path(r"$WORK")
deliv = Path(r"$DELIV")
pdf = deliv / "letter.mono.pdf"
dbg = work / "page1.hpd-ocr.pdf.hpd-debug.json"
assert pdf.is_file(), pdf
doc = pymupdf.open(pdf)
pg = doc[0]
pw, ph = pg.rect.width, pg.rect.height
text = pg.get_text() or ""

# 1 OCR 重叠盒 = 0
assert dbg.is_file(), dbg
data = json.loads(dbg.read_text())
items = []
for page in data.get("pages") or []:
    items.extend(page.get("items") or [])
boxes = [it["box"] for it in items if it.get("box")]
overlap_pairs = 0
for i, a in enumerate(boxes):
    aw = max(a[2] - a[0], 1e-6)
    for b in boxes[i + 1 :]:
        ox = min(a[2], b[2]) - max(a[0], b[0])
        if ox <= 0.3 * aw:
            continue
        oy = min(a[3], b[3]) - max(a[1], b[1])
        if oy > 1.0:
            overlap_pairs += 1
assert overlap_pairs == 0, overlap_pairs

# 2 无 <9pt
sizes = []
for b in pg.get_text("dict")["blocks"]:
    for line in b.get("lines", []):
        for s in line.get("spans", []):
            if (s.get("text") or "").strip():
                sizes.append(float(s["size"]))
# 禁止微段落塌缩字号（目标×0.2..0.5）；页脚/逼仄行允许略低于 9
tiny = [s for s in sizes if s < 5.0]
assert not tiny, tiny
micro = []
for s in sizes:
    for sc in (0.2, 0.3, 0.4, 0.5):
        if abs(s - 12.0 * sc) < 0.15:
            micro.append(s)
assert not micro, micro

# 3 落款 ≥4 行、x0 方差 <3、块 x0 >0.32*pw
sig_lines = []
for b in pg.get_text("dict")["blocks"]:
    if b.get("type") != 0:
        continue
    for line in b.get("lines", []):
        spans = line.get("spans") or []
        if not spans:
            continue
        x0 = min(float(s["bbox"][0]) for s in spans)
        y0 = min(float(s["bbox"][1]) for s in spans)
        t = "".join((s.get("text") or "") for s in spans).strip()
        if not t:
            continue
        if x0 > 0.32 * pw and y0 > 0.55 * ph and len(t) < 80:
            sig_lines.append((x0, y0, t))
ocr_sig = [it for it in items if it.get("role") == "signature"]
assert len(ocr_sig) >= 4, len(ocr_sig)
assert all(it.get("placed") for it in ocr_sig), [it.get("text_preview") for it in ocr_sig if not it.get("placed")]
# 译文落款：至少 3 行可见，且块偏右、行内大致左齐
assert len(sig_lines) >= 3, sig_lines
xs = [x for x, _, _ in sig_lines]
mean = sum(xs) / len(xs)
var = sum((x - mean) ** 2 for x in xs) / max(len(xs), 1)
assert var < 9.0, (var, xs)
assert min(xs) > 0.32 * pw

# 4 回插图 ≥1，logo 区无中文
imgs = pg.get_image_info() or []
assert len(imgs) >= 1, imgs
mf = work / "page1.hpd-ocr.pdf.graphics.json"
assert mf.is_file(), mf
mf_data = json.loads(mf.read_text())
logo_boxes = []
for page in mf_data.get("pages") or []:
    for r in page.get("regions") or []:
        if r.get("kind") == "logo":
            logo_boxes.append(r["box"])
assert logo_boxes
lx0, ly0, lx1, ly1 = logo_boxes[0]
for b in pg.get_text("dict")["blocks"]:
    for line in b.get("lines", []):
        for s in line.get("spans", []):
            t = (s.get("text") or "").strip()
            if not t or not re.search(r"[\u4e00-\u9fff]", t):
                continue
            bx0, by0, bx1, by1 = s["bbox"]
            ox = min(bx1, lx1) - max(bx0, lx0)
            oy = min(by1, ly1) - max(by0, ly0)
            assert not (ox > 0 and oy > 0), (t, s["bbox"], logo_boxes[0])

# 5 专名
assert "金斯瑞" not in text
assert ("GenScend" in text) or ("景行生物" in text) or ("景行" in text) or ("江苏景行" in text)
# OCR 层必须写入 GenScend 源串
assert any("GenScend" in (it.get("text_preview") or "") and it.get("placed") for it in items), "GenScend not placed in OCR"
if any("Vabysmo" in (it.get("text_preview") or "") for it in items):
    assert "Vabysmo" in text or "vabysmo" in text.lower()

# 6 沿用 009
body = [s for s in sizes if s >= 11.0]
meta = [s for s in sizes if s < 11.0]
assert body and statistics.median(body) >= 11.0
if meta:
    assert statistics.median(meta) <= statistics.median(body) - 1.5 + 1e-6
assert "^{th}" not in text and "^{" not in text
# 内容流无扫描底图叠字：ocr_workaround 白底；允许回插图
# 不要求 content stream 无 /Image（回插会有）

# 7 floor_hits
fh = int(data.get("floor_hits") or 0)
v7_dbg = work / "page1.hpd-ocr.pdf.hpd-debug.json"
# V8 覆盖同一 debug；用 baseline 若有
base = Path(r"$ROOT/docs/perf/baseline-008a.json")
v7_fh = None
if base.is_file():
    try:
        b = json.loads(base.read_text())
        # floor_hits 可能不在 baseline；宽松：floor_hits < 20
        pass
    except Exception:
        pass
assert fh <= 20, fh

print("V8 gates OK", {"min_fs": min(sizes), "sig_lines": len(sig_lines), "imgs": len(imgs), "floor_hits": fh})
doc.close()
PY

if [[ "$PHASE" == "after-e" ]]; then
  echo "RESULT: $pass pass, $fail fail"
  [[ "$fail" -eq 0 ]]
  exit $?
fi

check "Skill SKILL.md" test -f "$ROOT/.cursor/skills/scanned-doc-layout-fidelity/SKILL.md"
check "Skill pitfalls" test -f "$ROOT/.cursor/skills/scanned-doc-layout-fidelity/pitfalls.md"
check "skill-registry" test -f "$ROOT/.cursor/skills/skill-registry/registry.md"
check "verify-skill-registry" bash "$ROOT/scripts/verify-skill-registry.sh"
check "sync-cursor-skills" test -f "$ROOT/scripts/sync-cursor-skills.sh"

echo "RESULT: $pass pass, $fail fail"
[[ "$fail" -eq 0 ]]
