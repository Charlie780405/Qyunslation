#!/usr/bin/env bash
# verify-plan-005.sh — PLAN-005 Word/扫描/图片
# 用法: bash scripts/verify-plan-005.sh [baseline|after-a|after-b|after-c|after-d]

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHASE="${1:-baseline}"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
OFFICE_ENV="/home/dev/pdf2zh/office.env"
CADDY="/home/dev/qyunsgen/config/Caddyfile-production-public"

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

check "PLAN-005 纲领" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005-office-image.md"
check "005a 子计划" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005a-scanned-pdf-hpd.md"
check "005b 子计划" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005b-word-sidecar.md"
check "005c 子计划" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005c-image-overlay.md"
check "005d 子计划" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005d-archive.md"
check "005e 子计划" test -f "$ROOT/docs/plans/PLAN-005-office-image/PLAN-005e-unified-entry-gate.md"
check "hpd_ocr.py 入库" test -f "$ROOT/scripts/hpd_ocr.py"
check "apply-pdf2zh-hpd.py" test -f "$ROOT/scripts/apply-pdf2zh-hpd.py"

case "$PHASE" in
  baseline) ;;
  after-a|after-b|after-c|after-d)
    check "pdf2zh hpd re-export" test -f /home/dev/pdf2zh/hpd_ocr.py
    check "gui HPD 补丁" grep -q '_hpd_retried\|pdf_needs_hpd' "$GUI"
    check "pdf2zh.service ExecStartPre HPD" grep -q 'apply-pdf2zh-hpd.py' "$ROOT/scripts/pdf2zh.service"
    check "HPD health" curl -fsS --max-time 8 http://100.67.66.123:8120/health
    check "pdf2zh active" systemctl --user is-active pdf2zh.service
    check "baseline-005a" test -f "$ROOT/docs/perf/baseline-005a.json"
    ;;
  *)
    echo "FAIL: 未知阶段 $PHASE"
    fail=$((fail + 1))
    ;;
esac

if [[ "$PHASE" == "after-b" || "$PHASE" == "after-c" || "$PHASE" == "after-d" ]]; then
  check "office.env 存在" test -f "$OFFICE_ENV"
  check "office.env temp=0" grep -q 'DOCUTRANSLATE_TEMPERATURE=0' "$OFFICE_ENV"
  check "office.env concurrent=4" grep -q 'DOCUTRANSLATE_CONCURRENT=4' "$OFFICE_ENV"
  check "office.env 35b" grep -q 'qwen3.6:35b-a3b' "$OFFICE_ENV"
  check "office unit 模板" test -f "$ROOT/scripts/qyunslation-office.service"
  check "office service active" systemctl --user is-active qyunslation-office.service
  check "8010 HTTP" bash -c 'c=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:8010/); test "$c" = 200 -o "$c" = 307 -o "$c" = 302'
  check "Caddy translate 主站块" grep -q 'https://translate.qyunsgen.com' "$CADDY"
  check "translate 仍 7860" grep -A5 'translate.qyunsgen.com' "$CADDY" | grep -q '7860'
fi

if [[ "$PHASE" == "after-c" || "$PHASE" == "after-d" ]]; then
  check "image_translate 无 27b" bash -c "! grep -q 'qwen3.6:27b' '$ROOT/qyunslation/extensions/image_translate.py'"
  check "image_translate 用 35b" grep -q '35b-a3b' "$ROOT/qyunslation/extensions/image_translate.py"
  check "overlay CLI" test -f "$ROOT/scripts/hpd-overlay-image.py"
fi

if [[ "$PHASE" == "after-d" ]]; then
  check "office_out 目录" test -d /home/dev/pdf2zh/office_out
  check "office archive watch 脚本" test -f "$ROOT/scripts/office-archive-watch.py"
  check "005e office-route 补丁" test -f "$ROOT/scripts/apply-pdf2zh-office-route.py"
  check "005e WT 启用" test -f "$ROOT/docs/walkthroughs/WT-005e-unified-entry.md"
  check "gui office 路由" grep -q '_qy_is_office_sidecar_file' "$GUI"
  check "旧 office 域名 301→translate" grep -A3 'office.qyunsgen.com' "$CADDY" | grep -q 'translate.qyunsgen.com'
fi

echo "verify-plan-005 [$PHASE]: $pass/$((pass + fail))"
test "$fail" -eq 0
