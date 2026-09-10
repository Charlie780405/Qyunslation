#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-038g product polish gate.
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
run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then
    pass "$label"
  else
    fail "$label"
    tail -n 40 "$log"
  fi
}

[[ -x "$PY" ]] || { printf 'SUMMARY: FAIL blocked=1 missing venv python\n'; exit 1; }

# --- scripts / contracts ---
[[ -f "$ROOT/scripts/apply-pdf2zh-038g-session-cancel.py" ]] \
  && pass "038g session-cancel script" \
  || fail "missing apply-pdf2zh-038g-session-cancel.py"

[[ -f "$ROOT/scripts/apply-pdf2zh-brand.py" ]] \
  && pass "brand script present" \
  || fail "missing apply-pdf2zh-brand.py"

grep -q 'apply-pdf2zh-038g-session-cancel.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "pdf2zh.service has 038g ExecStartPre" \
  || fail "pdf2zh.service missing 038g session-cancel"

grep -q 'apply-pdf2zh-038g-session-cancel.py' "$ROOT/docs/contracts/pdf2zh-patch-order.md" \
  && pass "patch-order lists 038g" \
  || fail "pdf2zh-patch-order.md missing 038g"

grep -q 'SiliconFlow' "$ROOT/scripts/apply-pdf2zh-brand.py" \
  && grep -q 'visible=False' "$ROOT/scripts/apply-pdf2zh-brand.py" \
  && pass "brand scrub hides SiliconFlow ack" \
  || fail "brand script missing SiliconFlow hide"

# --- config (runtime, host-local; not in git) ---
CFG="/home/dev/pdf2zh/config.toml"
AUTH="/home/dev/pdf2zh/auth.csv"
if [[ -f "$CFG" ]]; then
  grep -Eq 'auth_file\s*=\s*".*auth\.csv"' "$CFG" \
    && pass "config auth_file set" \
    || fail "config.toml auth_file not set"
  grep -Eq 'glossaries\s*=\s*".*proper-nouns\.csv' "$CFG" \
    && pass "config glossaries set" \
    || fail "config.toml glossaries not set"
else
  fail "missing /home/dev/pdf2zh/config.toml"
fi

if [[ -f "$AUTH" ]]; then
  [[ "$(stat -c '%a' "$AUTH")" == "600" ]] \
    && pass "auth.csv mode 600" \
    || fail "auth.csv mode not 600"
  grep -q ',' "$AUTH" \
    && pass "auth.csv has user,pass" \
    || fail "auth.csv empty/malformed"
else
  fail "missing /home/dev/pdf2zh/auth.csv"
fi

# --- live GUI markers (if site-packages present) ---
GUI="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
if [[ -f "$GUI" ]]; then
  grep -q 'PLAN-038g: per-session unload cancel' "$GUI" \
    && pass "live gui has session-cancel marker" \
    || fail "live gui missing PLAN-038g session-cancel"
  grep -q 'title="Qyunslation' "$GUI" \
    && pass "live gui title white-labeled" \
    || fail "live gui title not Qyunslation"
else
  fail "live pdf2zh gui.py missing"
fi

# --- DOCX continued tables ---
run_pass "038g DOCX continued tests" "$STAGE_DIR/docx.log" \
  "$PY" -m pytest -q --no-cov tests/structure/test_plan038g_docx_continued.py

# --- optional live auth probe (skip if service down) ---
if ss -ltn 2>/dev/null | grep -q ':7860'; then
  code_no="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/config || true)"
  if [[ "$code_no" == "401" ]]; then
    pass "live /config requires auth (401)"
  else
    fail "live /config expected 401 got ${code_no:-none}"
  fi
  if [[ -f /home/dev/pdf2zh/office.env ]]; then
    # shellcheck disable=SC1091
    USER="$(grep '^QYUNSLATION_GUI_USER=' /home/dev/pdf2zh/office.env | cut -d= -f2-)"
    PASS="$(grep '^QYUNSLATION_GUI_PASS=' /home/dev/pdf2zh/office.env | cut -d= -f2-)"
    if [[ -n "$USER" && -n "$PASS" ]]; then
      code_ok="$(
        curl -sS -c "$STAGE_DIR/ck" -o /dev/null -w '%{http_code}' \
          -X POST 'http://127.0.0.1:7860/login' \
          -H 'Content-Type: application/x-www-form-urlencoded' \
          --data-urlencode "username=$USER" \
          --data-urlencode "password=$PASS" || true
      )"
      if [[ "$code_ok" == "200" ]]; then
        cfg_code="$(curl -sS -b "$STAGE_DIR/ck" -o "$STAGE_DIR/cfg.json" -w '%{http_code}' \
          http://127.0.0.1:7860/config || true)"
        if [[ "$cfg_code" == "200" ]] && grep -q 'Qyunslation' "$STAGE_DIR/cfg.json"; then
          pass "live login + branded /config"
        else
          fail "live login ok but /config not branded (${cfg_code})"
        fi
      else
        fail "live /login failed (${code_ok})"
      fi
    else
      fail "office.env missing QYUNSLATION_GUI_USER/PASS"
    fi
  else
    fail "missing office.env for auth probe"
  fi
else
  pass "skip live auth probe (7860 down)"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
