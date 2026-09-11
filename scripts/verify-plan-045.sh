#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-045 literature PDF fidelity gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
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

PLAN_DIR="$ROOT/docs/plans/PLAN-045-literature-pdf-fidelity"
[[ -f "$PLAN_DIR/PLAN-045-literature-pdf-fidelity.md" ]] \
  && pass "PLAN-045 charter" || fail "missing PLAN-045 charter"
for f in PLAN-045a-clinical-lexicon.md PLAN-045b-references-glued.md \
  PLAN-045c-il-sanitize.md PLAN-045d-image-panel-size.md \
  PLAN-045e-literature-table-size.md PLAN-045f-verify-docs.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

grep -q 'clear or almost clear' "$ROOT/glossaries/clinical-lifecycle.csv" \
  && pass "045a lexicon phrase" || fail "045a missing clear/almost clear"
grep -q '_resolve_glossary_path\|merged.csv' "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "045a image glossary default" || fail "045a glossary path"
grep -q '1Langanan\|(?=[A-Z]' "$ROOT/qyunslation/structure/references.py" \
  && pass "045b glued ENTRY_RE" || fail "045b ENTRY_RE"
grep -q 'strip_il_markup\|IL_MARKUP_LEAK' "$ROOT/qyunslation/structure/text_sanitize.py" \
  && pass "045c sanitize helper" || fail "045c helper"
[[ -f "$ROOT/scripts/apply-pdf2zh-045c-sanitize.py" ]] \
  && pass "045c patcher" || fail "missing 045c patcher"
grep -q 'apply-pdf2zh-045c-sanitize.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "045c in service" || fail "045c not in pdf2zh.service"
grep -q 'PANEL_TIER\|panel_letter\|TIER_K_FLOOR\|SOURCE_INK_LEFT' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "045d panel/k/erase" || fail "045d missing"
grep -q 'source_p75\|TABLE_SIZE_SOURCE_P75' "$ROOT/qyunslation/structure/role_fitter.py" \
  && pass "045e source_p75" || fail "045e missing"
grep -q 'table_size_mode' "$ROOT/scripts/pdf_table_translate.py" \
  && pass "045e wired" || fail "045e not wired"
grep -q 'panel_letter\|TIER_K_FLOOR\|擦除上限 2\|SOURCE_INK_LEFT' \
  "$ROOT/.cursor/skills/image-overlay-translation/SKILL.md" \
  && pass "SK-Q002 045d notes" || fail "SK-Q002 missing 045d"
grep -q 'IL_MARKUP_LEAK\|SOURCE_OVERLAY\|SOURCE_INK_LEFT' \
  "$ROOT/docs/plans/PLAN-042-regulatory-translation-quality/error-taxonomy.md" \
  && pass "taxonomy 045 codes" || fail "taxonomy missing 045 codes"

IL_PY="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
CREATER_PY="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/il_translator.py"
if [[ -f "$IL_PY" ]] && grep -q '_QY_033H_PRESERVE' "$IL_PY"; then
  pass "033h patch present"
else
  fail "033h patch missing on site-packages"
fi
if [[ -f "$CREATER_PY" ]] && grep -q '_QY_045C_SANITIZE\|PLAN-045c' "$CREATER_PY"; then
  pass "045c patch present"
else
  # apply once then recheck
  if "$PY" "$ROOT/scripts/apply-pdf2zh-045c-sanitize.py" >"$STAGE_DIR/045c-apply.log" 2>&1 \
    && grep -q '_QY_045C_SANITIZE\|PLAN-045c' "$CREATER_PY"; then
    pass "045c patch applied"
  else
    fail "045c patch missing"
  fi
fi

run_pass "045 compile" "$STAGE_DIR/compile.log" "$PY" -m compileall -q \
  qyunslation/structure/references.py \
  qyunslation/structure/text_sanitize.py \
  qyunslation/structure/role_fitter.py \
  qyunslation/extensions/image_translate.py \
  scripts/pdf_table_translate.py \
  scripts/apply-pdf2zh-045c-sanitize.py

run_pass "045 focused tests" "$STAGE_DIR/tests.log" \
  timeout --signal=INT --kill-after=10s 240s "$PY" -m pytest -q -o addopts= \
    tests/glossary/test_plan045_lexicon.py \
    tests/structure/test_plan045_references.py \
    tests/structure/test_plan045_sanitize.py \
    tests/structure/test_plan045_table_size.py \
    tests/extensions/test_plan045_image_panel.py \
    tests/structure/test_references.py

run_pass "039 regression" "$STAGE_DIR/039.log" bash "$ROOT/scripts/verify-plan-039.sh"
run_pass "033h regression" "$STAGE_DIR/033h.log" bash "$ROOT/scripts/verify-plan-033h.sh"

SAMPLE="${QYUNSLATION_PLAN045_SAMPLE:-}"
if [[ -z "$SAMPLE" || ! -f "$SAMPLE" ]]; then
  blocked "sample missing (set QYUNSLATION_PLAN045_SAMPLE)"
else
  if SAMPLE="$SAMPLE" "$PY" - <<'PY'
import os, re, sys
import pymupdf
from qyunslation.structure.text_sanitize import strip_il_markup, has_il_markup_leak
from qyunslation.structure.references import is_reference_heading, is_reference_entry

path = os.environ["SAMPLE"]
doc = pymupdf.open(path)
try:
    blob = "\n".join(page.get_text() for page in doc)
finally:
    doc.close()
# 源样：确认可识别 References；译文检查留给 EN_OUTPUT
if not any(is_reference_heading(line) for line in blob.splitlines()[:80]) and "References" not in blob:
    print("WARN: no References heading in sample text layer")
print("sample_ok pages=%d chars=%d" % (len(blob.split("---") or [1]), len(blob)))
sys.exit(0)
PY
  then pass "045 sample readable"
  else fail "045 sample probe"
  fi

  OUT="${QYUNSLATION_PLAN045_EN_OUTPUT:-}"
  if [[ -z "$OUT" || ! -f "$OUT" ]]; then
    blocked "EN output missing (set QYUNSLATION_PLAN045_EN_OUTPUT after retranslate)"
  else
    if OUT="$OUT" "$PY" - <<'PY'
import os, re, sys
import pymupdf
from qyunslation.structure.text_sanitize import has_il_markup_leak
from qyunslation.structure.references import is_reference_heading

path = os.environ["OUT"]
doc = pymupdf.open(path)
try:
    pages = [page.get_text() for page in doc]
finally:
    doc.close()
blob = "\n".join(pages)
fail = 0
if "皮肤清晰" in blob:
    print("FAIL: residual 皮肤清晰")
    fail = 1
if has_il_markup_leak(blob) or "<span" in blob.lower():
    print("FAIL: IL span leak")
    fail = 1
# References 区：标题之后少中文译句（允许专名原样）
in_refs = False
zh_in_refs = 0
for line in blob.splitlines():
    if is_reference_heading(line):
        in_refs = True
        continue
    if in_refs and re.search(r"[\u4e00-\u9fff]", line):
        # 标题行「参考文献」可中文；条目不应大段中文
        if not is_reference_heading(line):
            zh_in_refs += 1
if zh_in_refs > 2:
    print(f"FAIL: references Chinese lines={zh_in_refs}")
    fail = 1
sys.exit(fail)
PY
    then pass "045 EN output checks"
    else fail "045 EN output checks"
    fi
  fi
fi

printf 'SUMMARY: %s blocked=%s fail=%s\n' \
  "$([[ "$FAILURES" -eq 0 ]] && echo PASS || echo FAIL)" \
  "$BLOCKED" "$FAILURES"
[[ "$FAILURES" -eq 0 ]]
