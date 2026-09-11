#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-043 regulatory form label leakage gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  else
    PY="$ROOT/.venv/bin/python"
  fi
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=0 fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-043-regulatory-form-label-leakage"
[[ -f "$PLAN_DIR/PLAN-043-regulatory-form-label-leakage.md" ]] \
  && pass "PLAN-043 charter" || fail "missing PLAN-043 charter"
for f in PLAN-043a-writeback-fix.md PLAN-043b-glossary-fragments.md \
         PLAN-043c-table-chain-delivery.md PLAN-043d-verify-gates.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

grep -q 'post_translate_paragraph' "$ROOT/scripts/apply-pdf2zh-042b-short-label.py" \
  && pass "043a patcher uses post_translate" || fail "043a patcher missing post_translate"
grep -q '药物名称' "$ROOT/glossaries/regulatory-form-fields.csv" \
  && pass "043b form glossary" || fail "043b glossary missing"

run_pass "043 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/table_translate.py \
  qyunslation/structure/table_qc.py \
  qyunslation/structure/table_attribution.py \
  qyunslation/structure/regulatory_entities.py \
  scripts/apply-pdf2zh-042b-short-label.py \
  scripts/pdf_table_translate.py

run_pass "043 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 180s "$PY" -m pytest -q -o addopts= \
    tests/structure/test_plan043_quality.py \
    tests/structure/test_plan042_quality.py

# 042b live patch marker
IL="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
if [[ -f "$IL" ]] && grep -q 'post_translate_paragraph' "$IL" \
  && ! grep -q 'set_paragraph_translated(paragraph, _qy_direct)' "$IL"; then
  pass "042b live BabelDOC patch"
else
  fail "042b live patch not applied — run apply-pdf2zh-042b-short-label.py"
fi

EN_OUT="${QYUNSLATION_PLAN043_EN_OUTPUT:-}"
if [[ -z "$EN_OUT" || ! -f "$EN_OUT" ]]; then
  blocked "EN mono missing (set QYUNSLATION_PLAN043_EN_OUTPUT after retranslate)"
else
  if SAMPLE="$EN_OUT" "$PY" - <<'PY'
import os, re, sys
import pymupdf
from qyunslation.structure.page_qc import scan_page_text_qc

sample = os.environ["SAMPLE"]
doc = pymupdf.open(sample)
try:
    text = doc[0].get_text("text")
finally:
    doc.close()

labels = [
    "登记号", "试验状态", "进行中", "申请人联系人", "首次公示信息日期", "申请人名称",
    "一、题目和背景信息", "相关登记号", "试验专业题目", "试验通俗题目", "方案最新版本号",
    "二、申请人信息", "联系人邮政地址", "三、临床试验信息",
    "试验分类", "安全性和有效性", "试验分期", "设计类型", "平行分组", "随机化", "盲法", "双盲",
    "试验范围", "国内试验", "年龄", "性别", "男+女", "健康受试者", "否", "无", "生物制品", "临床研究",
    "药物名称", "药物类型", "适应症", "版本日期", "周清红",
]
hits = [lb for lb in labels if lb in text]
if hits:
    print("L1 labels still present:", hits[:8], "count=", len(hits))
    sys.exit(1)
if "Zhou Qinghong" not in text and "周清红" in text:
    print("person name not translated")
    sys.exit(1)
cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
print("page1_cjk", cjk)
if cjk >= 177:
    print("CJK not improved vs 042b regression baseline 177")
    sys.exit(1)
qc = scan_page_text_qc(pymupdf.open(sample)[0], expect_target_lang="en", max_cjk_when_en=0)
pymupdf.open(sample).close()
if qc.cjk_chars > 0:
    print("PAGE_CJK_RESIDUE chars", qc.cjk_chars)
    sys.exit(1)
print("sample gate ok")
PY
  then pass "043 real sample page1 L1 gate"
  else fail "043 real sample page1 L1 gate"; fi
fi

reg_rc=0
timeout --signal=INT --kill-after=10s 240s bash "$ROOT/scripts/verify-plan-042.sh" \
  >"$STAGE_DIR/reg.log" 2>&1 || reg_rc=$?
if [[ $reg_rc -eq 0 ]]; then
  pass "041/042 regression"
elif [[ $reg_rc -eq 2 ]]; then
  pass "041/042 regression (sample blocked ok)"
else
  fail "041/042 regression"
  tail -n 40 "$STAGE_DIR/reg.log"
fi

if [[ "$BLOCKED" -gt 0 && "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%d fail=0\n' "$BLOCKED"
  exit 2
fi
if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d blocked=%d\n' "$FAILURES" "$BLOCKED"
exit 1
