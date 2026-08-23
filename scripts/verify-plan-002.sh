#!/usr/bin/env bash
# verify-plan-002.sh — PLAN-002 拓扑/切流断言
# 用法: bash scripts/verify-plan-002.sh [baseline|after-a|after-b|after-c|after-d]
# 默认 baseline：只断言现网勘察事实，不要求已装 pdf2zh。

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-baseline}"
CADDY="/home/dev/qyunsgen/config/Caddyfile-production-public"
HOME_SVC="/home/dev/homepage/config/services.yaml"

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

title_of() {
  curl -fsS --max-time 15 "$1" | grep -oE '<title>[^<]+</title>' | head -1
}

check "PLAN 纲领存在" test -f "$ROOT/docs/plans/PLAN-002-babeldoc-replace-translate/PLAN-002-babeldoc-replace-translate.md"
check "homepage href 仍是 translate.qyunsgen.com" grep -q 'href: https://translate.qyunsgen.com' "$HOME_SVC"
check "Caddy 有 translate 站点块" grep -q 'https://translate.qyunsgen.com' "$CADDY"
check "本机 8010 或公网仍可达其一" bash -c 'curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:8010/ || curl -fsS --max-time 15 -o /dev/null https://translate.qyunsgen.com/'

case "$PHASE" in
  baseline)
    check "Caddy 仍反代 8010（未切流）" bash -c "awk '/https:\\/\\/translate\\.qyunsgen\\.com/,/^}/' \"$CADDY\" | grep -q '127.0.0.1:8010'"
    t="$(title_of http://127.0.0.1:8010/ || true)"
    if echo "$t" | grep -q 'Qyunslation'; then
      echo "PASS: :8010 标题含 Qyunslation ($t)"
      pass=$((pass + 1))
    else
      echo "FAIL: :8010 标题不是 Qyunslation ($t)"
      fail=$((fail + 1))
    fi
    ;;
  after-a)
    check "pdf2zh_next 可执行" bash -c 'command -v pdf2zh_next || test -x "$HOME/.local/bin/pdf2zh_next"'
    check "公网仍是 Qyunslation" bash -c 'curl -fsS --max-time 15 https://translate.qyunsgen.com/ | grep -q Qyunslation'
    ;;
  after-b)
    check "7860 HTTP 200" bash -c 'c=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:7860/); test "$c" = 200'
    check "公网仍是 Qyunslation" bash -c 'curl -fsS --max-time 15 https://translate.qyunsgen.com/ | grep -q Qyunslation'
    ;;
  after-c)
    check "Caddy 反代 7860" bash -c "awk '/https:\\/\\/translate\\.qyunsgen\\.com/,/^}/' \"$CADDY\" | grep -q '127.0.0.1:7860'"
    check "公网不再是 Qyunslation 标题" bash -c '! curl -fsS --max-time 15 https://translate.qyunsgen.com/ | grep -q "<title>荃信翻译 · Qyunslation</title>"'
    check "7860 HTTP 200" bash -c 'c=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:7860/); test "$c" = 200'
    ;;
  after-d)
    check "Caddy 反代 7860" bash -c "awk '/https:\\/\\/translate\\.qyunsgen\\.com/,/^}/' \"$CADDY\" | grep -q '127.0.0.1:7860'"
    check "docutranslate 未在跑" bash -c 'st=$(systemctl is-active docutranslate.service 2>/dev/null || true); test "$st" != active'
    check "8010 无监听" bash -c '! ss -lntp | grep -q ":8010 "'
    ;;
  *)
    echo "FAIL: 未知阶段 $PHASE"
    fail=$((fail + 1))
    ;;
esac

echo "verify-plan-002 [$PHASE]: $pass/$((pass + fail))"
test "$fail" -eq 0
