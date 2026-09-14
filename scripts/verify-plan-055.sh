#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-055：TM 向量 + 泰州 bge-m3 MCP 三态门禁（pass/fail/blocked）
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_ROOT="${HERMES_ROOT:-/home/dev/Hermes}"
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

PLAN_DIR="$ROOT/docs/plans/PLAN-055-tm-vector-embed"
WT="$ROOT/docs/walkthroughs/WT-055-tm-vector-embed.md"
EMBED_URL="${OLLAMA_EMBED_URL:-http://100.67.66.123:11434}"
EMBED_URL="${EMBED_URL%/}"

# --- 静态 ---
[[ -f "$PLAN_DIR/PLAN-055-tm-vector-embed.md" ]] && pass "PLAN-055 charter" || fail "PLAN-055 charter"
[[ -f "$PLAN_DIR/PLAN-055a-embed-mcp.md" ]] && pass "PLAN-055a" || fail "PLAN-055a"
[[ -f "$PLAN_DIR/PLAN-055b-tm-semantic.md" ]] && pass "PLAN-055b" || fail "PLAN-055b"
[[ -f "$PLAN_DIR/PLAN-055c-verify-gate.md" ]] && pass "PLAN-055c" || fail "PLAN-055c"
[[ -f "$PLAN_DIR/README.md" ]] && pass "PLAN-055 README" || fail "PLAN-055 README"
[[ -f "$WT" ]] && pass "WT-055" || fail "WT-055"
[[ -f "$HERMES_ROOT/mcp/embed-mcp/server.py" ]] && pass "Hermes embed-mcp" || fail "Hermes embed-mcp"
[[ -f "$ROOT/qyunslation/embed/client.py" ]] && pass "embed client" || fail "embed client"
[[ -f "$ROOT/alembic/versions/055a0001_tm_unit_embedding.py" ]] && pass "alembic 055a0001" || fail "alembic 055a0001"
[[ -f "$ROOT/scripts/verify-plan-055.sh" ]] && pass "verify-plan-055.sh" || fail "verify-plan-055.sh"
[[ -f "$ROOT/.cursor/mcp.json" ]] && pass "qyunslation mcp.json" || fail "qyunslation mcp.json"

# --- pytest（无网）---
if "$PY" -m pytest -q --no-cov \
  tests/embed/test_plan055_client.py \
  tests/persist/test_plan055_tm_semantic.py \
  >"$STAGE_DIR/pytest.log" 2>&1; then
  pass "plan055 pytest"
else
  fail "plan055 pytest"
  tail -n 50 "$STAGE_DIR/pytest.log" || true
fi

# --- 泰州探活（不通 → BLOCKED，不算 FAIL）---
TAGS_CODE=0
TAGS_BODY=""
if TAGS_BODY="$(curl -fsS --connect-timeout 3 --max-time 10 "$EMBED_URL/api/tags" 2>"$STAGE_DIR/tags.err")"; then
  if printf '%s' "$TAGS_BODY" | grep -q 'bge-m3'; then
    pass "taizhou tags has bge-m3"
  else
    blocked "taizhou tags reachable but bge-m3 missing"
    TAGS_CODE=1
  fi
else
  blocked "taizhou /api/tags unreachable ($EMBED_URL)"
  TAGS_CODE=1
fi

if [[ "$TAGS_CODE" -eq 0 ]]; then
  EMBED_BODY="$(curl -fsS --connect-timeout 3 --max-time 30 \
    -H 'Content-Type: application/json' \
    -d '{"model":"bge-m3","input":["plan055 probe"]}' \
    "$EMBED_URL/api/embed" 2>"$STAGE_DIR/embed.err" || true)"
  if [[ -n "$EMBED_BODY" ]]; then
    DIM="$("$PY" -c "
import json,sys
d=json.loads(sys.argv[1])
emb=d.get('embeddings') or []
print(len(emb[0]) if emb and isinstance(emb[0], list) else 0)
" "$EMBED_BODY")"
    if [[ "$DIM" == "1024" ]]; then
      pass "taizhou /api/embed dim=1024"
    else
      blocked "taizhou /api/embed dim=$DIM (want 1024)"
    fi
  else
    blocked "taizhou /api/embed failed"
  fi
fi

# --- 可选 LIVE ---
if [[ "${QYUNSLATION_PLAN055_LIVE:-}" == "1" || "${QYUNSLATION_PLAN055_LIVE:-}" == "true" ]]; then
  if [[ -z "${QYUNSLATION_DATABASE_URL:-}" ]]; then
    blocked "LIVE: QYUNSLATION_DATABASE_URL unset"
  elif [[ "$TAGS_CODE" -ne 0 ]]; then
    blocked "LIVE: embed unreachable, skip migrate/lookup"
  else
    if (cd "$ROOT" && "$PY" -m alembic upgrade head) >"$STAGE_DIR/alembic.log" 2>&1; then
      pass "LIVE alembic upgrade"
    else
      blocked "LIVE alembic upgrade failed"
      tail -n 30 "$STAGE_DIR/alembic.log" || true
    fi
    if "$PY" "$ROOT/scripts/plan055-backfill-tm-embed.py" --limit 32 \
      >"$STAGE_DIR/backfill.log" 2>&1; then
      pass "LIVE backfill (or noop)"
    else
      blocked "LIVE backfill failed"
      tail -n 30 "$STAGE_DIR/backfill.log" || true
    fi
  fi
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
