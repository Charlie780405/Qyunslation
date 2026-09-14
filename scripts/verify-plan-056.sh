#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-056：应用栏方向开关 + 检查器可见性三态门禁
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

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL fail=1 blocked=0\n'
  exit 1
fi

PLAN="$ROOT/docs/plans/PLAN-056-appbar-inspector-ux"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
PATCH="$ROOT/scripts/apply-pdf2zh-050-workbench.py"

[[ -f "$PLAN/PLAN-056-appbar-inspector-ux.md" ]] && pass "PLAN-056 charter" || fail "PLAN-056 charter"
for f in PLAN-056a-appbar-direction.md PLAN-056b-inspector-help.md \
  PLAN-056c-verify-gate.md README.md; do
  [[ -f "$PLAN/$f" ]] && pass "$f" || fail "$f"
done
[[ -f "$ROOT/docs/walkthroughs/WT-056-appbar-inspector-ux.md" ]] && pass "WT-056" || fail "WT-056"
grep -q 'PLAN-056-appbar-inspector-ux' "$ROOT/docs/plans/README.md" \
  && pass "plans index 056" || fail "plans index 056"
grep -q 'PLAN-056' "$ROOT/docs/plans/PLAN-050-qyunslation-ui-ux/PLAN-050-qyunslation-ui-ux.md" \
  && pass "050 backlink 056" || fail "050 backlink 056"
grep -q 'qy-050-appbar' "$ROOT/docs/contracts/ui-runtime-050.md" \
  && pass "ui-runtime appbar anchor" || fail "ui-runtime appbar anchor"

if python3 - <<PY
from pathlib import Path
t = Path("$PATCH").read_text(encoding="utf-8")
css = t.split("JS_BLOCK", 1)[0]
raise SystemExit(0 if "translateX(100%)" not in css else 1)
PY
then
  pass "patch CSS no translateX drawer"
else
  fail "patch still has drawer translateX"
fi
grep -q 'qy_dir = gr.Radio' "$PATCH" && pass "patch qy_dir" || fail "patch qy_dir"
# 057 覆盖：检查器改为 Column；历史门禁接受 Column 或 Accordion
if grep -qE 'qy_inspector = gr\.(Column|Accordion)\(' "$PATCH"; then
  pass "patch inspector panel"
else
  fail "patch inspector panel"
fi
grep -q 'qy_dir.change' "$PATCH" && pass "patch dir sync" || fail "patch dir sync"
grep -q '禁止再写入 Gradio js=' "$PATCH" && pass "patch js= ban" || fail "patch js= ban"

if "$PY" -m pytest -q --no-cov \
  tests/ui/test_plan056_appbar.py \
  tests/ui/test_plan050_workbench_patch.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan056 pytest"
else
  fail "plan056 pytest"
  tail -n 40 "$STAGE_DIR/pytest.log" || true
fi

if [[ -f "$GUI" ]] \
  && grep -q 'qy_dir = gr.Radio' "$GUI" \
  && grep -qE 'qy_inspector = gr\.(Column|Accordion)\(' "$GUI" \
  && grep -q 'qy_dir.change' "$GUI" \
  && ! grep -q 'translateX(100%)' "$GUI" \
  && ! grep -q '_qy_050_workbench_js' "$GUI" \
  && ! grep -q '方向在左侧' "$GUI"; then
  pass "gui.py 056/057 chrome"
else
  fail "gui.py missing 056/057 chrome or js= still hijacked"
fi

if ss -ltn 2>/dev/null | grep -q ':7860'; then
  curl -sS -o "$STAGE_DIR/login.html" http://127.0.0.1:7860/ || true
  if grep -q 'Qyunslation' "$STAGE_DIR/login.html"; then
    pass "live login page"
  else
    fail "live login page"
  fi
  if [[ -f /home/dev/pdf2zh/office.env ]]; then
    USER=$(grep '^QYUNSLATION_GUI_USER=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    PASS=$(grep '^QYUNSLATION_GUI_PASS=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    if [[ -n "${USER:-}" && -n "${PASS:-}" ]]; then
      curl -sS -c "$STAGE_DIR/ck" -o /dev/null \
        -X POST 'http://127.0.0.1:7860/login' \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode "username=$USER" \
        --data-urlencode "password=$PASS" || true
      curl -sS -b "$STAGE_DIR/ck" -o "$STAGE_DIR/app.html" http://127.0.0.1:7860/ || true
      if grep -q '英→中' "$STAGE_DIR/app.html" && grep -q 'qy-050-appbar' "$STAGE_DIR/app.html"; then
        pass "live appbar direction"
      else
        fail "live appbar direction (need deploy)"
      fi
      if grep -q 'translateX(100%)' "$STAGE_DIR/app.html"; then
        fail "live HTML still has translateX drawer"
      else
        pass "live HTML no translateX"
      fi
    else
      blocked "GUI user/pass unset"
    fi
  else
    blocked "office.env missing"
  fi
else
  blocked "7860 down"
fi

if [[ "${QYUNSLATION_PLAN056_LIVE:-}" == "1" || "${QYUNSLATION_PLAN056_LIVE:-}" == "true" ]]; then
  pass "LIVE flag set (browser point-check required outside script)"
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%s fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0\n'
exit 0
