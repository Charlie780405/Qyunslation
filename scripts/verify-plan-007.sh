#!/usr/bin/env bash
# verify-plan-007.sh — PLAN-007 扫描件一对一译文渲染
# 用法: bash scripts/verify-plan-007.sh [baseline|after-a|after-b|after-c|after-d]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-baseline}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
CFG="/home/dev/pdf2zh/config.toml"
UNIT="$ROOT/scripts/pdf2zh.service"
IL="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
OLLAMA_PY="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/translator/translator_impl/ollama.py"

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

check "PLAN-007 纲领" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007-scanned-fidelity.md"
check "007a 子计划" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007a-page1-harness.md"
check "007b 子计划" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007b-hpd-geometry.md"
check "007c 子计划" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007c-ocr-workaround.md"
check "007d 子计划" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007d-json-mode.md"
check "007e 子计划" test -f "$ROOT/docs/plans/PLAN-007-scanned-fidelity/PLAN-007e-fullrun-deploy.md"
check "bench 脚本" test -f "$ROOT/scripts/bench-scanned-page1.sh"
check "pdf2zh active" systemctl --user is-active pdf2zh.service
check "7860 HTTP" bash -c 'c=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:7860/); test "$c" = 200 -o "$c" = 302 -o "$c" = 307'
check "HPD health" curl -fsS --max-time 8 http://100.67.66.123:8120/health

case "$PHASE" in
  baseline) ;;
  after-a)
    check "baseline-007a" test -f "$ROOT/docs/perf/baseline-007a.json"
    check "baseline 含 V0" grep -q '"V0"' "$ROOT/docs/perf/baseline-007a.json"
    ;;
  after-b)
    check "baseline-007a" test -f "$ROOT/docs/perf/baseline-007a.json"
    check "hpd 无 12.0 硬上限" bash -c "! grep -q 'min(12.0' '$ROOT/scripts/hpd_ocr.py'"
    check "hpd 有 _fit_fontsize" grep -q 'def _fit_fontsize' "$ROOT/scripts/hpd_ocr.py"
    check "hpd smoke" python3 "$ROOT/scripts/test_hpd_ocr_smoke.py"
    ;;
  after-c)
    check "gui ocr_workaround×2" bash -c "test \$(grep -c 'settings.pdf.ocr_workaround = True' '$GUI') -ge 2"
    check "config ocr_workaround 仍 false" grep -q 'ocr_workaround = false' "$CFG"
    check "apply 幂等" bash -c "python3 '$ROOT/scripts/apply-pdf2zh-hpd.py' 2>&1 | grep -q 'already patched'"
    ;;
  after-d)
    check "baseline-007a" test -f "$ROOT/docs/perf/baseline-007a.json"
    check "hpd 有 _fit_fontsize" grep -q 'def _fit_fontsize' "$ROOT/scripts/hpd_ocr.py"
    check "hpd smoke" python3 "$ROOT/scripts/test_hpd_ocr_smoke.py"
    check "gui ocr_workaround×2" bash -c "test \$(grep -c 'settings.pdf.ocr_workaround = True' '$GUI') -ge 2"
    check "config ocr_workaround 仍 false" grep -q 'ocr_workaround = false' "$CFG"
    check "config OpenAICompatible off" grep -q 'openaicompatible = false' "$CFG"
    check "config Ollama on" grep -q 'ollama = true' "$CFG"
    check "unit Ollama" grep -q 'enabled-services Ollama' "$UNIT"
    check "gui enabled Ollama" grep -q 'enabled_services = "Ollama"' "$CFG"
    check "unit batch paras" grep -q 'PDF2ZH_LLM_BATCH_PARAS' "$UNIT"
    check "ollama think=False" grep -q 'think=False' "$OLLAMA_PY"
    check "ocr-base patch script" test -f "$ROOT/scripts/apply-pdf2zh-ocr-base.py"
    check "ocr-base applied" grep -q '_qy_ocr_base_ops' "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/backend/pdf_creater.py"
    check "hpd strips backslash" grep -q '剥离易弄坏 LLM JSON 的反斜杠' "$ROOT/scripts/hpd_ocr.py"
    check "throughput IL batch" grep -q '_PDF2ZH_LLM_BATCH_TOKENS' "$IL"
    check "WT-007" test -f "$ROOT/docs/walkthroughs/WT-007-scanned-fidelity.md"
    check "Ollama tags" curl -fsS --max-time 8 http://100.67.66.123:11434/api/tags
    ;;
  *)
    echo "FAIL: 未知阶段 $PHASE"
    fail=$((fail + 1))
    ;;
esac

echo "verify-plan-007 [$PHASE]: $pass/$((pass + fail))"
test "$fail" -eq 0
