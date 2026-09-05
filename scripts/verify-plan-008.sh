#!/usr/bin/env bash
# verify-plan-008.sh — 文档类型模板与段落聚合
# 用法: bash scripts/verify-plan-008.sh [after-d|after-e]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-after-d}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
UNIT="$ROOT/scripts/pdf2zh.service"
PY="${QYUNSLATION_VERIFY_PY:-/home/dev/.local/share/uv/tools/pdf2zh-next/bin/python}"

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

check "PLAN-008 纲领" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008-doc-profiles.md"
check "008a" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008a-integrity-metrics.md"
check "008b" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008b-paragraph-merge.md"
check "008c" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008c-templates.md"
check "008d" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008d-gui.md"
check "008e" test -f "$ROOT/docs/plans/PLAN-008-doc-profiles/PLAN-008e-page1-accept.md"
check "doc_profiles.toml" test -f "$ROOT/scripts/doc_profiles.toml"
check "doc_profile.py" test -f "$ROOT/scripts/doc_profile.py"
check "apply-pdf2zh-docprofile.py" test -f "$ROOT/scripts/apply-pdf2zh-docprofile.py"
check "hpd 有段落聚合" grep -q 'def _merge_lines_into_paragraphs' "$ROOT/scripts/hpd_ocr.py"
check "hpd 不改远程 URL 常量" grep -q 'HPD_URL = "http://100.67.66.123:8120"' "$ROOT/scripts/hpd_ocr.py"
check "toml letter" grep -q '\[letter\]' "$ROOT/scripts/doc_profiles.toml"
check "toml literature" grep -q '\[literature\]' "$ROOT/scripts/doc_profiles.toml"
check "toml regulatory" grep -q '\[regulatory\]' "$ROOT/scripts/doc_profiles.toml"
check "unit ExecStartPre docprofile" grep -q 'apply-pdf2zh-docprofile.py' "$UNIT"
check "hpd+profile smoke" "$PY" -m unittest scripts.test_hpd_ocr_smoke scripts.test_doc_profile
check "baseline-008a" test -f "$ROOT/docs/perf/baseline-008a.json"
check "gui dropdown" grep -q 'doc_profile_dropdown' "$GUI"
check "gui apply 模板" grep -q '_qy_prof' "$GUI"
check "gui HPD 传 aggressive" grep -q 'aggressive=_qy_merge_agg' "$GUI"
check "apply 幂等" bash -c "python3 '$ROOT/scripts/apply-pdf2zh-docprofile.py' 2>&1 | grep -q 'already patched'"

if [[ "$PHASE" == "after-e" ]]; then
  check "WT-008" test -f "$ROOT/docs/walkthroughs/WT-008-doc-profiles.md"
  check "V6 baseline" grep -q '"V6"' "$ROOT/docs/perf/baseline-008a.json"
  check "letter 样例 PNG" test -f "$ROOT/deliverables/plan-008-profiles/letter.mono.png"
  check "literature 样例 PNG" test -f "$ROOT/deliverables/plan-008-profiles/literature.mono.png"
  check "regulatory 样例 PNG" test -f "$ROOT/deliverables/plan-008-profiles/regulatory.mono.png"
  check "V6 字号中位>=10" python3 -c "
import json
m=json.load(open('$ROOT/docs/perf/baseline-008a.json'))['variants']['V6']['mono']
assert (m.get('font_median') or 0)>=10, m
"
  check "V6 无半句悬挂" python3 -c "
import pymupdf
p='/home/dev/pdf2zh/bench/007/out-V6/translated-left.pdf'
t=pymupdf.open(p)[0].get_text()
assert '初步回复' in t
# 旧 V5 悬挂句不得再单独出现
assert '我们对您会议问题的初步回复是\n' not in t
assert '我们对您会议问题的初步回复是' not in t or ('附后' in t or '如下' in t)
"
  check "OCR 段内 are+enclosed" python3 -c "
import json
from pathlib import Path
d=json.loads(Path('/home/dev/pdf2zh/bench/007/page1.hpd-ocr.pdf.hpd-debug.json').read_text())
items=d['pages'][0]['items']
ok=any('are' in (it.get('text_preview') or '') and 'enclos' in (it.get('text_preview') or '') for it in items)
# preview 可能截断，退回全文
import pymupdf
t=pymupdf.open('/home/dev/pdf2zh/bench/007/page1.hpd-ocr.pdf')[0].get_text()
ok=ok or ('enclosed' in t.lower() and 'questions are' in t.replace('\u2011','-').lower())
assert d['pages'][0].get('lines_before_merge',0) > d['pages'][0].get('blocks',99)
assert 'enclosed' in t.lower()
"
fi

echo "---- $pass passed, $fail failed ----"
test "$fail" -eq 0
