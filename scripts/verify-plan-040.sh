#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-040 upload settle + auth shell gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
ROUTES="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/gradio/routes.py"

[[ -f "$ROOT/docs/plans/PLAN-040-upload-auth-ux/PLAN-040-upload-auth-ux.md" ]] \
  && pass "PLAN-040 charter" || fail "missing PLAN-040 charter"
for f in PLAN-040a-auth-shell.md PLAN-040b-upload-settle.md PLAN-040c-docs-verify.md; do
  [[ -f "$ROOT/docs/plans/PLAN-040-upload-auth-ux/$f" ]] && pass "$f" || fail "missing $f"
done

[[ -f "$ROOT/scripts/apply-pdf2zh-040a-auth-shell.py" ]] && pass "040a script" || fail "missing 040a"
[[ -f "$ROOT/scripts/apply-pdf2zh-040b-upload-settle.py" ]] && pass "040b script" || fail "missing 040b"
[[ -f "$ROOT/scripts/apply-pdf2zh-040d-refresh-keep.py" ]] && pass "040d script" || fail "missing 040d"
[[ -f "$ROOT/docs/plans/PLAN-040-upload-auth-ux/PLAN-040d-refresh-keep.md" ]] \
  && pass "PLAN-040d-refresh-keep.md" || fail "missing 040d doc"

grep -q 'apply-pdf2zh-040a-auth-shell.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "service has 040a" || fail "service missing 040a"
grep -q 'apply-pdf2zh-040b-upload-settle.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "service has 040b" || fail "service missing 040b"
grep -q 'apply-pdf2zh-040d-refresh-keep.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "service has 040d" || fail "service missing 040d"
grep -q 'apply-pdf2zh-040a-auth-shell.py' "$ROOT/docs/contracts/pdf2zh-patch-order.md" \
  && pass "patch-order 040a" || fail "patch-order missing 040a"
grep -q 'apply-pdf2zh-040d-refresh-keep.py' "$ROOT/docs/contracts/pdf2zh-patch-order.md" \
  && pass "patch-order 040d" || fail "patch-order missing 040d"

[[ -f /home/dev/pdf2zh/gradio.cookie_id ]] && pass "cookie_id file" || fail "missing gradio.cookie_id"

if [[ -f "$ROUTES" ]]; then
  grep -q 'PLAN-040a: stable cookie_id' "$ROUTES" && pass "routes cookie_id" || fail "routes cookie_id"
  grep -q 'PLAN-040a: persist tokens' "$ROUTES" && pass "routes token persist" || fail "routes token persist"
  grep -q 'PLAN-040a: short login page' "$ROUTES" && pass "routes short login" || fail "routes short login"
else
  fail "missing gradio routes.py"
fi

if [[ -f "$GUI" ]]; then
  grep -q 'function checkAuth' "$GUI" && pass "gui checkAuth" || fail "gui checkAuth"
  grep -q 'r.status === 401' "$GUI" && pass "gui 401 banner" || fail "gui 401 banner"
  grep -q 'PLAN-040b: upload settle' "$GUI" && pass "gui upload settle" || fail "gui upload settle"
  grep -q 'PLAN-040d: refresh must NOT cancel' "$GUI" && pass "gui 040d refresh-keep" || fail "gui 040d missing"
  if grep -A20 'def _cancel_active_translation_on_unload' "$GUI" | grep -q 'keeping translation for session'; then
    pass "unload keeps translation"
  else
    fail "unload still schedules cancel"
  fi
  if grep -A35 'async def stop_translate_file' "$GUI" | grep -q 'task.cancel\|current_task'; then
    pass "manual stop still present"
  else
    fail "stop_translate_file lost cancel"
  fi
  hidden=$(grep -c 'show_progress="hidden"' "$GUI" || true)
  [[ "$hidden" -ge 3 ]] && pass "hidden progress >=3 ($hidden)" || fail "hidden progress count=$hidden"
  grep -q '_qy_upload_settle_js' "$GUI" && pass "upload settle js" || fail "upload settle js"
  grep -q 'PLAN-040a: default auth_message' "$GUI" && pass "default auth_message" || fail "auth_message"
else
  fail "missing gui.py"
fi

# live probes if up
if ss -ltn 2>/dev/null | grep -q ':7860'; then
  code=$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/config || true)
  if [[ "$code" == "401" ]]; then
    pass "live /config 401 without cookie"
  else
    fail "live /config expected 401 got ${code:-none}"
  fi
  # auth short page (not 349KB shell)
  curl -sS -o "$STAGE_DIR/index.html" http://127.0.0.1:7860/ || true
  idx_bytes=$(wc -c <"$STAGE_DIR/index.html" | tr -d ' ')
  if grep -q 'Qyunslation' "$STAGE_DIR/index.html" \
    && grep -q 'name="username"' "$STAGE_DIR/index.html" \
    && [[ "$idx_bytes" -lt 50000 ]]; then
    pass "index short login page (${idx_bytes}B)"
  elif grep -q 'auth_required' "$STAGE_DIR/index.html"; then
    fail "index still full shell (${idx_bytes}B) with auth_required"
  else
    fail "index missing short login (${idx_bytes}B)"
  fi
  # login + restart persistence: login then check token file
  if [[ -f /home/dev/pdf2zh/office.env ]]; then
    USER=$(grep '^QYUNSLATION_GUI_USER=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    PASS=$(grep '^QYUNSLATION_GUI_PASS=' /home/dev/pdf2zh/office.env | cut -d= -f2-)
    if [[ -n "$USER" && -n "$PASS" ]]; then
      curl -sS -c "$STAGE_DIR/ck" -o /dev/null -w '%{http_code}' \
        -X POST 'http://127.0.0.1:7860/login' \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        --data-urlencode "username=$USER" \
        --data-urlencode "password=$PASS" >"$STAGE_DIR/login.code"
      if [[ "$(cat "$STAGE_DIR/login.code")" == "200" ]]; then
        pass "live login 200"
        cfg=$(curl -sS -b "$STAGE_DIR/ck" -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/config || true)
        [[ "$cfg" == "200" ]] && pass "live /config 200 after login" || fail "config after login=$cfg"
        # logged-in GET / should be full app shell
        curl -sS -b "$STAGE_DIR/ck" -o "$STAGE_DIR/app.html" http://127.0.0.1:7860/ || true
        app_bytes=$(wc -c <"$STAGE_DIR/app.html" | tr -d ' ')
        if [[ "$app_bytes" -gt 100000 ]]; then
          pass "logged-in index is app shell (${app_bytes}B)"
        else
          fail "logged-in index too small (${app_bytes}B)"
        fi
        if [[ -f /home/dev/pdf2zh/gradio-tokens.json ]]; then
          pass "tokens file written"
        else
          fail "tokens file missing after login"
        fi
      else
        fail "live login failed ($(cat "$STAGE_DIR/login.code"))"
      fi
    fi
  fi
else
  pass "skip live probes (7860 down)"
fi

[[ -f "$ROOT/docs/walkthroughs/WT-040-upload-auth-ux.md" ]] \
  && pass "WT-040" || fail "missing WT-040"

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
