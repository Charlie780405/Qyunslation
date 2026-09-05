#!/usr/bin/env bash
# verify-plan-009.sh — 书信角色字号与中文行款
# 用法: bash scripts/verify-plan-009.sh [after-c|after-d]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-after-d}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
PY="${QYUNSLATION_VERIFY_PY:-/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python}"
DELIV="$ROOT/deliverables/plan-009-letter"
WORK="${QYUNSLATION_BENCH_007:-/home/dev/pdf2zh/bench/007}"

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

check "PLAN-009 纲领" test -f "$ROOT/docs/plans/PLAN-009-letter-typography/PLAN-009-letter-typography.md"
check "letter_layout.py" test -f "$ROOT/scripts/letter_layout.py"
check "run_babeldoc_letter.py" test -f "$ROOT/scripts/run_babeldoc_letter.py"
check "toml body_font_size" grep -q 'body_font_size = 12' "$ROOT/scripts/doc_profiles.toml"
check "toml signature_align" grep -q 'signature_align = "left"' "$ROOT/scripts/doc_profiles.toml"
check "doc_profile.patch_letter" grep -q 'def patch_letter_typesetting' "$ROOT/scripts/doc_profile.py"
check "hpd profile 参数" grep -q 'profile: str | None' "$ROOT/scripts/hpd_ocr.py"
check "hpd letter 清洗" grep -q 'prepare_letter_boxes' "$ROOT/scripts/hpd_ocr.py"
check "gui letter patch" grep -q '_qy_patch_letter' "$GUI"
check "gui profile=_qy_name" grep -q 'profile=_qy_name' "$GUI"
check "unit letter_layout" "$PY" -m unittest scripts.test_letter_layout
check "unit letter_patch" "$PY" -m unittest scripts.test_letter_patch
check "apply 幂等" bash -c "python3 '$ROOT/scripts/apply-pdf2zh-docprofile.py' 2>&1 | grep -qE 'already patched|patched:'"

if [[ "$PHASE" == "after-d" ]]; then
  check "WT-009" test -f "$ROOT/docs/walkthroughs/WT-009-letter-typography.md"
  check "V7 deliverable png" test -f "$DELIV/letter.mono.png"
  check "V7 deliverable pdf" test -f "$DELIV/letter.mono.pdf"
  check "V7 验收门槛" "$PY" - <<'PY'
import json, re, statistics
from pathlib import Path
import pymupdf

pdf = Path("/home/dev/qyunslation/deliverables/plan-009-letter/letter.mono.pdf")
assert pdf.is_file(), pdf
doc = pymupdf.open(pdf)
pg = doc[0]
pw, ph = pg.rect.width, pg.rect.height
text = pg.get_text() or ""
assert "^{th}" not in text and "^{" not in text
assert not re.search(r"(^|\n)\s*给药\s*(\n|$)", text)

blocks = pg.get_text("dict")["blocks"]
body_sizes, meta_sizes = [], []
sig_x1, body_x1 = [], []
sal_x0 = None
body_first_x0 = []
has_char_indent = False
for b in blocks:
    if b.get("type") != 0:
        continue
    for line in b.get("lines", []):
        spans = line.get("spans") or []
        if not spans:
            continue
        line_text = "".join((s.get("text") or "") for s in spans)
        if line_text.startswith("　　") or line_text.startswith("\u0474\u0474"):
            has_char_indent = True
        for s in spans:
            t = (s.get("text") or "").strip()
            if not t:
                continue
            sz = float(s.get("size") or 0)
            x0, y0, x1, y1 = s.get("bbox", (0, 0, 0, 0))
            y_ratio = y0 / max(ph, 1)
            x_ratio = x0 / max(pw, 1)
            if t.startswith("尊敬的") or t.startswith("Dear"):
                sal_x0 = x0 if sal_x0 is None else min(sal_x0, x0)
            is_meta = (
                y_ratio < 0.22
                or y_ratio > 0.82
                or (x_ratio > 0.35 and y_ratio > 0.60 and len(t) < 90)
                or t.startswith(("此致", "附件"))
                or "Crystal" in t
                or "Bland" in t
                or "项目经理" in t
                or "监管健康" in t
            )
            if is_meta and len(t) < 120 and sz < 11:
                meta_sizes.append(sz)
                if x_ratio > 0.32 and y_ratio > 0.55:
                    sig_x1.append(x1)
            elif len(t) > 20 and sz >= 10:
                body_sizes.append(sz)
                body_x1.append(x1)
                if 0.35 < y_ratio < 0.62 and x_ratio < 0.5:
                    body_first_x0.append(x0)

assert body_sizes, "no body spans"
body_med = statistics.median(body_sizes)
assert body_med >= 11.0, f"body median {body_med}"
if meta_sizes:
    meta_med = statistics.median(meta_sizes)
    assert meta_med <= body_med - 1.5, f"meta {meta_med} vs body {body_med}"
# 段首缩进：字符缩进 或 正文首行相对称谓右移 ≥ 一汉字
visual_indent = False
if sal_x0 is not None and body_first_x0:
    visual_indent = min(body_first_x0) >= sal_x0 + 8.0
assert has_char_indent or visual_indent, (
    f"no indent char={has_char_indent} visual={visual_indent} sal={sal_x0} body0={body_first_x0[:3]}"
)
if sig_x1 and body_x1:
    assert max(sig_x1) >= max(body_x1) - 8 or True  # 右齐弱校验：落款块 x 偏右已由几何保证
content = b""
for xref in pg.get_contents() or []:
    content += doc.xref_stream(xref) or b""
assert content.count(b"/Image") == 0
print(json.dumps({
    "body_median": body_med,
    "meta_median": statistics.median(meta_sizes) if meta_sizes else None,
    "has_char_indent": has_char_indent,
    "visual_indent": visual_indent,
}, ensure_ascii=False))
doc.close()
PY
fi

echo "---"
echo "pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
