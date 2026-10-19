#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-079：QA 阻断分级、术语审核准入、对照视图定位的门禁。三态：PASS / FAIL / BLOCKED。
# 不覆盖已跟踪的 qyunslation/static/app（构建只输出到临时目录）；浏览器走查、影子灰度属于无法自动验证的项，标 BLOCKED。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
LOGDIR="${QYUNSLATION_VERIFY_LOG_DIR:-${TMPDIR:-/tmp}}"
FAILURES=0
BLOCKED=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

REQUIRED=(
  "docs/plans/PLAN-079-qa-gate-and-term-triage/PLAN-079-qa-gate-and-term-triage.md"
  "docs/walkthroughs/WT-079-qa-gate-and-term-triage.md"
  "scripts/qa/plan079_baseline.py"
  "scripts/qa/plan079_shadow_report.py"
  "scripts/qa/plan079_probe_eval.py"
  "qyunslation/pipeline/qa/term_review.py"
)
for path in "${REQUIRED[@]}"; do
  [[ -f "$ROOT/$path" ]] && pass "file $path" || fail "missing $path"
done

# 默认开关必须是 legacy：不部署、不配置时行为不变
if [[ -x "$PY" ]]; then
  mode=$(cd "$ROOT" && env -u QYUNSLATION_TERM_GATE_MODE "$PY" -c "from qyunslation.pipeline.qa.term_review import term_gate_mode; print(term_gate_mode())" 2>/dev/null)
  [[ "$mode" == "legacy" ]] && pass "term gate defaults to legacy" || fail "term gate default is '$mode', expected legacy"

  mapfile -t TESTS < <(cd "$ROOT" && ls tests/*/test_plan079*.py tests/workbench/test_plan061_candidate_rules.py tests/pipeline/test_plan078b_registry.py 2>/dev/null)
  if (cd "$ROOT" && "$PY" -m pytest -q -o addopts= -p no:cacheprovider "${TESTS[@]}" >"$LOGDIR/verify-plan-079-backend.log" 2>&1); then
    pass "PLAN-079 backend tests (${#TESTS[@]} files)"
  else
    fail "PLAN-079 backend tests (see $LOGDIR/verify-plan-079-backend.log)"
  fi
else
  blocked "Python interpreter unavailable"
fi

if [[ -d "$ROOT/frontend/node_modules" ]]; then
  if (cd "$ROOT/frontend" && npx vitest run src/next >"$LOGDIR/verify-plan-079-frontend.log" 2>&1); then
    pass "frontend vitest (src/next)"
  else
    fail "frontend vitest (see $LOGDIR/verify-plan-079-frontend.log)"
  fi
  BUILD_DIR="$(mktemp -d)"
  if (cd "$ROOT/frontend" && npx vite build --outDir "$BUILD_DIR" --emptyOutDir >/dev/null 2>&1); then
    pass "frontend builds (temp output)"
    # 真实浏览器：需要含 node_modules/playwright 的目录；没有就如实标 BLOCKED，不当作通过
    PW_DIR="${QY_PLAYWRIGHT_DIR:-$HOME/.cache/qyunslation-browser-tests}"
    if [[ -d "$PW_DIR/node_modules/playwright" && -x "$PY" ]] && command -v node >/dev/null 2>&1; then
      # Playwright 找不到与自身版本匹配的 WebKit 时，退到缓存里最新的一份
      if [[ -z "${QY_WEBKIT_EXEC:-}" ]]; then
        QY_WEBKIT_EXEC="$(ls -d "$HOME"/.cache/ms-playwright/webkit-*/pw_run.sh 2>/dev/null | sort -V | tail -1)"
        export QY_WEBKIT_EXEC
      fi
      PDF_DIR="$(mktemp -d)"
      "$PY" "$ROOT/scripts/browser/plan079_make_pdfs.py" "$PDF_DIR" >/dev/null 2>&1
      if QY_BUILD_DIR="$BUILD_DIR" QY_PDF_DIR="$PDF_DIR" QY_PLAYWRIGHT_DIR="$PW_DIR" \
          node "$ROOT/scripts/browser/plan079-locate-check.mjs" >"$LOGDIR/verify-plan-079-browser.log" 2>&1; then
        pass "browser locate check ($(tail -1 "$LOGDIR/verify-plan-079-browser.log"))"
      else
        fail "browser locate check (see $LOGDIR/verify-plan-079-browser.log)"
      fi
      # 批准 -> 完成页（下载）-> 回到 QA 页
      if QY_BUILD_DIR="$BUILD_DIR" QY_PLAYWRIGHT_DIR="$PW_DIR" \
          node "$ROOT/scripts/browser/plan079-complete-check.mjs" >"$LOGDIR/verify-plan-079-complete-browser.log" 2>&1; then
        pass "browser approve-to-export flow ($(tail -1 "$LOGDIR/verify-plan-079-complete-browser.log"))"
      else
        fail "browser approve-to-export flow (see $LOGDIR/verify-plan-079-complete-browser.log)"
      fi
      # F8：上传页拖放、空闲/执行中的轮询请求数（Chromium + WebKit）
      if QY_BUILD_DIR="$BUILD_DIR" QY_PLAYWRIGHT_DIR="$PW_DIR" \
          node "$ROOT/scripts/browser/plan079-workbench-check.mjs" >"$LOGDIR/verify-plan-079-workbench-browser.log" 2>&1; then
        pass "browser drag-drop and polling check ($(tail -1 "$LOGDIR/verify-plan-079-workbench-browser.log"))"
      else
        fail "browser drag-drop and polling check (see $LOGDIR/verify-plan-079-workbench-browser.log)"
      fi
      rm -rf "$PDF_DIR"
    else
      blocked "browser locate check: Playwright not found at $PW_DIR (set QY_PLAYWRIGHT_DIR)"
    fi
  else
    fail "frontend build"
  fi
  rm -rf "$BUILD_DIR"
else
  blocked "frontend dependencies unavailable"
fi

blocked "登录后的真实页面走查（F1）、Firefox 与触屏实机需要账号或设备，尚未进行"
blocked "影子灰度（QYUNSLATION_TERM_GATE_MODE=shadow 一个工作周）与 enforce 切换尚未进行"

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
