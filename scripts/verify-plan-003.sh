#!/usr/bin/env bash
# verify-plan-003.sh — PLAN-003 吞吐加速断言
# 用法: bash scripts/verify-plan-003.sh [baseline|after-a|after-b|after-c]

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-baseline}"
CONFIG="/home/dev/pdf2zh/config.toml"
ARCHIVE_ENV="/home/dev/pdf2zh/archive.env"
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

check "PLAN-003 纲领存在" test -f "$ROOT/docs/plans/PLAN-003-translate-throughput/PLAN-003-translate-throughput.md"
check "003a 子计划存在" test -f "$ROOT/docs/plans/PLAN-003-translate-throughput/PLAN-003a-pipeline-fastwin.md"
check "003b 子计划存在" test -f "$ROOT/docs/plans/PLAN-003-translate-throughput/PLAN-003b-ollama-scheduling.md"
check "003c 子计划存在" test -f "$ROOT/docs/plans/PLAN-003-translate-throughput/PLAN-003c-job-cancel.md"
check "apply-pdf2zh-throughput.py 存在" test -f "$ROOT/scripts/apply-pdf2zh-throughput.py"
check "benchmark-ollama-003b.py 存在" test -f "$ROOT/scripts/benchmark-ollama-003b.py"

case "$PHASE" in
  baseline)
    ;;
  after-a|after-b|after-c)
    check "config 关自动术语" grep -q 'no_auto_extract_glossary = true' "$CONFIG"
    check "archive.env 含 SESSION_DIR" grep -q 'PDF2ZH_ARCHIVE_SESSION_DIR' "$ARCHIVE_ENV"
    check "watcher 脚本含 flock" grep -q 'flock' "$ROOT/scripts/pdf2zh-archive-watch.py"
    check "watcher active" systemctl --user is-active pdf2zh-archive-watch.service
    check "pdf2zh active" systemctl --user is-active pdf2zh.service
    check "7860 HTTP 200" bash -c 'c=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:7860/); test "$c" = 200'
    check "泰州 Ollama 探活" curl -fsS --max-time 8 http://100.67.66.123:11434/api/tags
    ;;
  *)
    echo "FAIL: 未知阶段 $PHASE"
    fail=$((fail + 1))
    ;;
esac

if [[ "$PHASE" == "after-a" || "$PHASE" == "after-b" || "$PHASE" == "after-c" ]]; then
  if [[ -n "$GUI" && -f "$GUI" ]]; then
    check "gui unload 补丁" grep -q 'demo.unload' "$GUI"
    check "gui stop_translate_file unload" grep -q 'stop_translate_file' "$GUI"
  else
    echo "FAIL: 找不到 pdf2zh gui.py"
    fail=$((fail + 1))
  fi
fi

if [[ "$PHASE" == "after-b" ]]; then
  check "baseline-003b.json 存在" test -f "$ROOT/docs/perf/baseline-003b.json"
fi

echo "verify-plan-003 [$PHASE]: $pass/$((pass + fail))"
test "$fail" -eq 0
