#!/usr/bin/env bash
# verify-plan-004.sh — PLAN-004 保质量再加速断言
# 用法: bash scripts/verify-plan-004.sh [baseline|after-a|after-b|after-c]

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-baseline}"
CONFIG="/home/dev/pdf2zh/config.toml"
OLLAMA_PY="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/translator/translator_impl/ollama.py"
IL_PY="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
GLOSSARY="/home/dev/pdf2zh/glossaries/qx027n.csv"

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

check "PLAN-004 纲领存在" test -f "$ROOT/docs/plans/PLAN-004-quality-throughput/PLAN-004-quality-throughput.md"
check "004a 子计划存在" test -f "$ROOT/docs/plans/PLAN-004-quality-throughput/PLAN-004a-inference-hygiene.md"
check "004b 子计划存在" test -f "$ROOT/docs/plans/PLAN-004-quality-throughput/PLAN-004b-skip-glossary-cache.md"
check "004c 子计划存在" test -f "$ROOT/docs/plans/PLAN-004-quality-throughput/PLAN-004c-llm-batch.md"
check "004d 子计划存在" test -f "$ROOT/docs/plans/PLAN-004-quality-throughput/PLAN-004d-vllm-gate.md"
check "apply-pdf2zh-throughput.py 存在" test -f "$ROOT/scripts/apply-pdf2zh-throughput.py"
check "deploy-taizhou-ollama-004a.sh 存在" test -f "$ROOT/scripts/deploy-taizhou-ollama-004a.sh"

case "$PHASE" in
  baseline)
    ;;
  after-a|after-b|after-c)
    check "config num_predict=512" grep -q 'num_predict = 512' "$CONFIG"
    check "ollama.py 封顶 1024" grep -q 'min(len(text) \* 5, 1024)' "$OLLAMA_PY"
    check "baseline-004a.json 存在" test -f "$ROOT/docs/perf/baseline-004a.json"
    check "baseline 含 observed_llama_server" python3 -c "import json; d=json.load(open('$ROOT/docs/perf/baseline-004a.json')); assert 'observed_llama_server' in d"
    check "泰州 Ollama 探活" curl -fsS --max-time 8 http://100.67.66.123:11434/api/tags
    check "pdf2zh active" systemctl --user is-active pdf2zh.service
    ;;
  *)
    echo "FAIL: 未知阶段 $PHASE"
    fail=$((fail + 1))
    ;;
esac

if [[ "$PHASE" == "after-b" || "$PHASE" == "after-c" ]]; then
  check "skip already-target-lang 补丁" grep -q '_pdf2zh_skip_already_target_lang' "$IL_PY"
  check "QX027 glossary 存在" test -f "$GLOSSARY"
  check "config glossaries 指向 qx027n" grep -q 'glossaries = "/home/dev/pdf2zh/glossaries/qx027n.csv"' "$CONFIG"
  check "仍关自动抽术语" grep -q 'no_auto_extract_glossary = true' "$CONFIG"
  check "gui cache 日志补丁" grep -q 'PLAN-004b cache' "$GUI"
fi

if [[ "$PHASE" == "after-c" ]]; then
  check "批阈值 400/8 补丁" grep -q 'PDF2ZH_LLM_BATCH_TOKENS' "$IL_PY"
  check "批阈值默认 400" grep -q '_PDF2ZH_LLM_BATCH_TOKENS = int' "$IL_PY"
  check "004d WT 关闭文档" test -f "$ROOT/docs/walkthroughs/WT-004d-vllm-gate-closed.md"
fi

echo "verify-plan-004 [$PHASE]: $pass/$((pass + fail))"
test "$fail" -eq 0
