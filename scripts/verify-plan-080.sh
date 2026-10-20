#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-080：PDF 译文完整性、字体统一、装饰线随文、人名职务保留、段落级 QA 的门禁。三态：PASS / FAIL / BLOCKED。
# BLOCKED 表示无法在本机验证（没有样本、没有部署权限），不计为通过。
#
# 可选环境变量：
#   QYUNSLATION_PLAN080_SAMPLE   源 PDF（真实样本不入库）
#   QYUNSLATION_PLAN080_OUTPUT   对应的译文 mono PDF（用修复后的代码重译得到）
#   QYUNSLATION_VERIFY_FULL=1    额外跑 tests/structure tests/pipeline tests/scripts tests/ui tests/workbench tests/api
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
LOGDIR="${QYUNSLATION_VERIFY_LOG_DIR:-${TMPDIR:-/tmp}}"
SITE="${QYUNSLATION_PDF2ZH_SITE:-$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages}"
FAILURES=0
BLOCKED=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-080-pdf-translation-completeness-and-typography/PLAN-080-pdf-translation-completeness-and-typography.md"
  "docs/plans/PLAN-080-pdf-translation-completeness-and-typography/PLAN-080h-manifest-schema-test-baseline.md"
  "docs/walkthroughs/WT-080-pdf-translation-completeness-and-typography.md"
  "scripts/qa/plan080_diagnose.py"
  "scripts/qa/plan080_trace_run.py"
  "scripts/qa/plan080_trace_report.py"
  "scripts/apply-pdf2zh-080c-fonts.py"
  "qyunslation/structure/font_policy.py"
  "qyunslation/structure/decoration_realign.py"
  "qyunslation/structure/entity_preserve.py"
  "qyunslation/structure/office_preserve.py"
  "docs/runbooks/plan-080-rollout.md"
  "qyunslation/pipeline/qa/pdf_layout.py"
  "docs/contracts/document-structure-manifest-v2.schema.json"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

if [[ ! -x "$PY" ]]; then
  blocked "Python interpreter unavailable ($PY)"
else
  # D3：新规则默认关闭。不部署、不配置时输出必须与以前一致。
  defaults=$(cd "$ROOT" && env -u QYUNSLATION_FONT_POLICY -u QYUNSLATION_DECORATION_REALIGN -u QYUNSLATION_LAYOUT_QA -u QYUNSLATION_OFFICE_PRESERVE "$PY" -c "
from qyunslation.structure.font_policy import font_policy_mode
from qyunslation.structure.decoration_realign import realign_mode
from qyunslation.pipeline.qa.pdf_layout import layout_qa_mode
from qyunslation.structure.office_preserve import office_preserve_enabled
print(font_policy_mode(), realign_mode(), layout_qa_mode(), 'on' if office_preserve_enabled() else 'off')" 2>/dev/null)
  [[ "$defaults" == "off off off off" ]] && pass "new post-processing rules default to off ($defaults)" || fail "unexpected defaults: '$defaults'"

  # 保留策略是默认开启的修复（不是可选开关）：编号问题段与背景句必须进入翻译，职务必须保留
  policy=$(cd "$ROOT" && "$PY" -c "
from qyunslation.structure import babeldoc_policy as bp
bp.reset_preserve_gate()
a = bp.paragraph_is_preserved('2. The protocol synopsis does not detail planned subgroup analyses for the primary endpoint.')
b = bp.paragraph_is_preserved('On June 12, 2026, Example Biopharma Co., Ltd. submitted this meeting request to discuss the proposed strategy and plan.')
c = bp.paragraph_is_preserved('Medical Director')
d = bp.paragraph_is_preserved('Clinical Pharmacology')
e = bp.paragraph_is_preserved('activity in patients with atopic dermatitis. J. Dermatol. Sci. 44, 93–99 (2006). 47. Bissonnette, R. et al. Clinical effects of an oral antagonist. Allergy 79, 924–936 (2024).')
print(a, b, c, d, e)" 2>/dev/null)
  [[ "$policy" == "False False True False True" ]] && pass "preserve policy: numbered items and prose are translated; titles and merged citations are kept" || fail "preserve policy unexpected: '$policy'"

  mapfile -t TESTS < <(cd "$ROOT" && ls tests/*/test_plan080*.py 2>/dev/null; ls tests/structure/test_manifest_contract.py tests/structure/test_manifest_store.py tests/structure/test_plan059_fidelity.py tests/ui/test_plan050_state_manifest.py 2>/dev/null)
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider "${TESTS[@]}" >"$LOGDIR/verify-plan-080-backend.log" 2>&1); then
    pass "PLAN-080 and 080h backend tests (${#TESTS[@]} files)"
  else
    fail "PLAN-080 backend tests (see $LOGDIR/verify-plan-080-backend.log)"
  fi

  mapfile -t RELATED < <(cd "$ROOT" && ls tests/structure/test_plan045_references.py tests/structure/test_plan033h_references_style.py tests/structure/test_plan074_frontmatter.py tests/pipeline/test_plan078b_registry.py tests/pipeline/test_plan071e_pdf_inspect.py tests/workbench/test_plan066e_runner.py 2>/dev/null)
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider "${RELATED[@]}" >"$LOGDIR/verify-plan-080-related.log" 2>&1); then
    pass "neighbouring suites still pass (references, front matter, QA registry, runner)"
  else
    fail "neighbouring suites (see $LOGDIR/verify-plan-080-related.log)"
  fi

  if [[ "${QYUNSLATION_VERIFY_FULL:-0}" == "1" ]]; then
    if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider --no-cov tests/structure tests/pipeline tests/scripts tests/ui tests/workbench tests/api >"$LOGDIR/verify-plan-080-full.log" 2>&1); then
      pass "full suites (structure, pipeline, scripts, ui, workbench, api)"
    else
      fail "full suites (see $LOGDIR/verify-plan-080-full.log)"
    fi
  else
    blocked "full suites skipped (set QYUNSLATION_VERIFY_FULL=1; about 10 minutes)"
  fi

  # 真实样本：重译后的 mono 不得再有整段漏译、字体与装饰线问题
  if [[ -n "${QYUNSLATION_PLAN080_SAMPLE:-}" && -n "${QYUNSLATION_PLAN080_OUTPUT:-}" \
        && -f "${QYUNSLATION_PLAN080_SAMPLE}" && -f "${QYUNSLATION_PLAN080_OUTPUT}" ]]; then
    codes=$(cd "$ROOT" && QYUNSLATION_LAYOUT_QA=on "$PY" -I -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from qyunslation.pipeline.qa.pdf_layout import check_output_layout
fs = check_output_layout(Path(sys.argv[1]), Path(sys.argv[2]))
print(','.join(sorted(f.code for f in fs)) or 'none')" "$QYUNSLATION_PLAN080_SAMPLE" "$QYUNSLATION_PLAN080_OUTPUT" 2>/dev/null)
    if [[ "$codes" == *UNTRANSLATED_PARAGRAPH* ]]; then
      fail "sample output still has untranslated paragraphs ($codes)"
    else
      pass "sample output has no untranslated paragraphs (layout QA: $codes)"
    fi
  else
    blocked "样本回归：设置 QYUNSLATION_PLAN080_SAMPLE 与 QYUNSLATION_PLAN080_OUTPUT（用修复后的代码重译得到）后才能验证"
  fi
fi

# 部署：补丁是否已装进翻译引擎（本机没有 pdf2zh.service 单元，无法替用户确认）
if [[ -f "$SITE/babeldoc/format/pdf/document_il/utils/fontmap.py" ]]; then
  if grep -q "_QY_080C_FONT_POLICY" "$SITE/babeldoc/format/pdf/document_il/utils/fontmap.py"; then
    pass "080c font patch is applied in the translation engine"
  else
    blocked "080c 字体补丁尚未装进翻译引擎（部署后执行 apply-pdf2zh-080c-fonts.py 并重启 pdf2zh）"
  fi
else
  blocked "找不到翻译引擎 site-packages（$SITE），无法确认补丁部署"
fi
ENGINE_IL="$SITE/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
if [[ -f "$ENGINE_IL" ]]; then
  if grep -q "_qy_033h_warn_once" "$ENGINE_IL"; then
    pass "033h preserve helper in the engine logs a warning when the policy cannot be imported"
  else
    blocked "引擎里的保留谓词仍是旧版（导入失败时静默关闭保留功能）；部署后执行 apply-pdf2zh-fidelity-033h.py 并重启 pdf2zh"
  fi
fi
blocked "生产启用与灰度（QYUNSLATION_FONT_POLICY、QYUNSLATION_DECORATION_REALIGN、QYUNSLATION_LAYOUT_QA、QYUNSLATION_OFFICE_PRESERVE）需要用户在运行环境设置"

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED fail=0 blocked=%s\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
exit 0
