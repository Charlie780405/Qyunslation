#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-054：正式 IdP（Authentik）门禁
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"
PUBLIC_BASE="${QYUNSLATION_PUBLIC_BASE:-https://translate.qyunsgen.com}"
AUTH_PUBLIC="${QYUNSLATION_AUTH_PUBLIC:-https://auth.qyunsgen.com}"
AK_URL="${AUTHENTIK_API_URL:-http://127.0.0.1:9000}"
AK_ENV="$ROOT/deploy/authentik/.env"
OFFICE_ENV="${QYUNSLATION_OFFICE_ENV:-/home/dev/pdf2zh/office.env}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

PLAN_DIR="$ROOT/docs/plans/PLAN-054-company-idp"
WT="$ROOT/docs/walkthroughs/WT-054-company-idp.md"

# --- 静态 ---
[[ -f "$PLAN_DIR/PLAN-054-company-idp.md" ]] && pass "PLAN-054 charter" || fail "PLAN-054 charter"
[[ -f "$PLAN_DIR/PLAN-054a-authentik-deploy.md" ]] && pass "PLAN-054a" || fail "PLAN-054a"
[[ -f "$PLAN_DIR/PLAN-054b-oidc-blueprint.md" ]] && pass "PLAN-054b" || fail "PLAN-054b"
[[ -f "$PLAN_DIR/PLAN-054c-cutover-verify.md" ]] && pass "PLAN-054c" || fail "PLAN-054c"
[[ -f "$PLAN_DIR/README.md" ]] && pass "PLAN-054 README" || fail "PLAN-054 README"
[[ -f "$WT" ]] && pass "WT-054" || fail "WT-054"
[[ -f "$ROOT/deploy/authentik/docker-compose.yml" ]] && pass "authentik compose" || fail "authentik compose"
[[ -f "$ROOT/deploy/authentik/blueprints/qyunslation-oidc.yaml" ]] && pass "blueprint yaml" || fail "blueprint yaml"
[[ -f "$ROOT/scripts/deploy-plan-054-authentik.sh" ]] && pass "deploy script" || fail "deploy script"
[[ -f "$ROOT/scripts/plan054-apply-blueprint.sh" ]] && pass "apply script" || fail "apply script"
[[ -f "$ROOT/scripts/verify-plan-054.sh" ]] && pass "verify script" || fail "verify script"

if [[ -f "$CADDYFILE" ]] && awk '/https:\/\/auth\.qyunsgen\.com/,/^}/' "$CADDYFILE" | grep -q '127.0.0.1:9000'; then
  pass "Caddyfile auth → 9000"
else
  fail "Caddyfile missing auth → 9000"
fi

if docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile \
  >"$STAGE_DIR/caddy-validate.log" 2>&1; then
  pass "caddy validate"
else
  fail "caddy validate"
  tail -n 20 "$STAGE_DIR/caddy-validate.log" || true
fi

# --- 本机 Authentik / pilot ---
if curl -fsS -o /dev/null --max-time 8 "$AK_URL/-/health/live/"; then
  pass "Authentik live :9000"
else
  fail "Authentik live :9000"
fi

if ss -tln | grep -q ':5556 '; then
  fail "pilot :5556 still listening (should be stopped)"
else
  pass "pilot :5556 stopped"
fi

if [[ -f "$OFFICE_ENV" ]] && grep -q 'auth.qyunsgen.com/application/o/qyunslation' "$OFFICE_ENV"; then
  pass "office.env points to Authentik issuer"
else
  fail "office.env not switched to Authentik issuer"
fi

# --- 公网 JWKS（DNS 未就绪 → BLOCKED） ---
JWKS_CODE="$(curl -sS -o "$STAGE_DIR/pub-jwks.json" -w '%{http_code}' --max-time 15 \
  "${AUTH_PUBLIC}/application/o/qyunslation/jwks/" 2>/dev/null || true)"
JWKS_CODE="${JWKS_CODE:-000}"
if [[ "$JWKS_CODE" == "200" ]] && grep -q '"keys"' "$STAGE_DIR/pub-jwks.json" 2>/dev/null; then
  pass "public JWKS 200"
else
  blocked "public JWKS unreachable (HTTP $JWKS_CODE) — add Cloudflare DNS for auth.qyunsgen.com"
fi

# 本机 JWKS（sidecar 实际拉取路径）
if curl -fsS --max-time 8 "$AK_URL/application/o/qyunslation/jwks/" | grep -q '"keys"'; then
  pass "local JWKS :9000"
else
  fail "local JWKS :9000"
fi

# --- E2E：client_credentials → 公网 API ---
if [[ ! -f "$AK_ENV" ]]; then
  blocked "deploy/authentik/.env missing; skip E2E"
else
  CLIENT_SECRET="$(grep -E '^QYUNSLATION_OIDC_CLIENT_SECRET=' "$AK_ENV" | head -1 | cut -d= -f2-)"
  if [[ -z "$CLIENT_SECRET" ]]; then
    blocked "client secret empty; skip E2E"
  else
    TOKEN_RESP="$(curl -sS --max-time 20 -X POST "$AK_URL/application/o/token/" \
      -H 'Host: auth.qyunsgen.com' -H 'X-Forwarded-Proto: https' \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      --data-urlencode 'grant_type=client_credentials' \
      --data-urlencode 'client_id=qyunslation' \
      --data-urlencode "client_secret=${CLIENT_SECRET}" \
      --data-urlencode 'scope=openid profile email tenant' 2>"$STAGE_DIR/token.err" || true)"
    TOKEN="$(printf '%s' "$TOKEN_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)"
    if [[ -z "$TOKEN" ]]; then
      blocked "M2M token failed: ${TOKEN_RESP:0:200}"
    else
      AUTH=(-H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json')
      SLUG="plan054-$(date +%s)"
      PROJ_BODY="$(curl -sS --max-time 20 -X POST "${PUBLIC_BASE}/api/v1/projects" \
        "${AUTH[@]}" -d "{\"slug\":\"${SLUG}\",\"name\":\"PLAN-054 verify\"}" \
        -w '\n%{http_code}' || true)"
      PROJ_CODE="$(printf '%s' "$PROJ_BODY" | tail -1)"
      PROJ_JSON="$(printf '%s' "$PROJ_BODY" | sed '$d')"
      PROJECT_ID="$(printf '%s' "$PROJ_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null || true)"
      if [[ -z "$PROJECT_ID" ]]; then
        fail "E2E create project failed (HTTP $PROJ_CODE): ${PROJ_JSON:0:300}"
      else
        SHA="$(printf 'plan054-e2e' | sha256sum | awk '{print $1}')"
        JOB_BODY="$(curl -sS --max-time 20 -X POST "${PUBLIC_BASE}/api/v1/jobs" \
          "${AUTH[@]}" \
          -d "{\"project_id\":\"${PROJECT_ID}\",\"source_sha256\":\"${SHA}\"}" \
          -w '\n%{http_code}' || true)"
        JOB_CODE="$(printf '%s' "$JOB_BODY" | tail -1)"
        JOB_JSON="$(printf '%s' "$JOB_BODY" | sed '$d')"
        JOB_ID="$(printf '%s' "$JOB_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null || true)"
        if [[ -z "$JOB_ID" ]]; then
          fail "E2E create job failed (HTTP $JOB_CODE): ${JOB_JSON:0:300}"
        else
          ENQ_BODY="$(curl -sS --max-time 20 -X POST "${PUBLIC_BASE}/api/v1/review/enqueue" \
            "${AUTH[@]}" \
            -d "{\"job_id\":\"${JOB_ID}\",\"segments\":[{\"source_text\":\"PLAN-054 E2E source\",\"machine_text\":\"PLAN-054 入队译文\",\"policy\":\"HUMAN_REVIEW\",\"role\":\"body\",\"block_id\":\"b054\"}]}" \
            -w '\n%{http_code}' || true)"
          ENQ_CODE="$(printf '%s' "$ENQ_BODY" | tail -1)"
          ENQ_JSON="$(printf '%s' "$ENQ_BODY" | sed '$d')"
          COUNT="$(printf '%s' "$ENQ_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("count",0))' 2>/dev/null || echo 0)"
          if [[ "$ENQ_CODE" == "200" && "$COUNT" -ge 1 ]]; then
            pass "public E2E review enqueue (count=$COUNT)"
          else
            fail "E2E enqueue expected count>=1 (HTTP $ENQ_CODE): ${ENQ_JSON:0:300}"
          fi
        fi
      fi
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
