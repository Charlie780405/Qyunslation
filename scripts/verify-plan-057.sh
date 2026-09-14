#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-057：壳层去重 + 高级区滚动三态门禁
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

PLAN="$ROOT/docs/plans/PLAN-057-chrome-dedupe"
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
PATCH="$ROOT/scripts/apply-pdf2zh-050-workbench.py"

[[ -f "$PLAN/PLAN-057-chrome-dedupe.md" ]] && pass "PLAN-057 charter" || fail "PLAN-057 charter"
for f in PLAN-057a-hide-lang-panels.md PLAN-057b-adv-scroll.md \
  PLAN-057c-verify-gate.md README.md; do
  [[ -f "$PLAN/$f" ]] && pass "$f" || fail "$f"
done
[[ -f "$ROOT/docs/walkthroughs/WT-057-chrome-dedupe.md" ]] && pass "WT-057" || fail "WT-057"
grep -q 'PLAN-057-chrome-dedupe' "$ROOT/docs/plans/README.md" \
  && pass "plans index 057" || fail "plans index 057"
grep -q 'PLAN-057' "$ROOT/docs/plans/PLAN-056-appbar-inspector-ux/PLAN-056-appbar-inspector-ux.md" \
  && pass "056 backlink 057" || fail "056 backlink 057"
grep -q 'visible=False' "$ROOT/docs/contracts/ui-runtime-050.md" \
  && pass "ui-runtime lang-row hidden" || fail "ui-runtime lang-row hidden"

grep -q 'qy_help = gr.Column(' "$PATCH" && pass "patch help Column" || fail "patch help Column"
grep -q 'qy_inspector = gr.Column(' "$PATCH" && pass "patch inspector Column" || fail "patch inspector Column"
if python3 - <<PY
from pathlib import Path
t = Path("$PATCH").read_text(encoding="utf-8").split("def verify", 1)[0]
raise SystemExit(0 if "qy_help = gr.Accordion(" not in t else 1)
PY
then
  pass "patch no help Accordion"
else
  fail "patch still has help Accordion"
fi
grep -q 'elem_classes=\["lang-row"\], visible=False' "$PATCH" \
  && pass "patch lang-row hidden" || fail "patch lang-row hidden"
grep -q 'min(55vh, 560px)' "$PATCH" && pass "patch adv scroll override" || fail "patch adv scroll override"
grep -q 'apply_adv_scroll' "$PATCH" && pass "patch adv scroll applier" || fail "patch adv scroll applier"
grep -q '禁止再写入 Gradio js=' "$PATCH" && pass "patch js= ban" || fail "patch js= ban"

if "$PY" -m pytest -q --no-cov \
  tests/ui/test_plan057_chrome_dedupe.py \
  tests/ui/test_plan050_workbench_patch.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan057 pytest"
else
  fail "plan057 pytest"
  tail -n 40 "$STAGE_DIR/pytest.log" || true
fi

if [[ -f "$GUI" ]] \
  && grep -Eq 'qy_dir = gr\.(Radio|Dropdown)' "$GUI" \
  && grep -q 'qy_help = gr.Column(' "$GUI" \
  && grep -q 'qy_inspector = gr.Column(' "$GUI" \
  && grep -q 'elem_classes=\["lang-row"\], visible=False' "$GUI" \
  && grep -q 'min(55vh, 560px)' "$GUI" \
  && ! grep -q 'min(38vh, 340px)' "$GUI" \
  && ! grep -q 'qy_help = gr.Accordion(' "$GUI" \
  && ! grep -q '_qy_050_workbench_js' "$GUI"; then
  pass "gui.py 057 chrome"
else
  fail "gui.py missing 057 chrome"
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
      if grep -q 'min(55vh, 560px)' "$STAGE_DIR/app.html"; then
        pass "live adv scroll css"
      else
        fail "live adv scroll css missing"
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
