#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-053：SaaS Caddy 对外 /api/v1 + 公网鉴权门禁
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"
PUBLIC_BASE="${QYUNSLATION_PUBLIC_BASE:-https://translate.qyunsgen.com}"
OIDC_MINT="${QYUNSLATION_OIDC_MINT_URL:-http://127.0.0.1:5556/token}"
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

PLAN_DIR="$ROOT/docs/plans/PLAN-053-saas-caddy-expose"
WT="$ROOT/docs/walkthroughs/WT-053-saas-caddy-expose.md"

# --- 静态 ---
[[ -f "$PLAN_DIR/PLAN-053-saas-caddy-expose.md" ]] && pass "PLAN-053 charter" || fail "PLAN-053 charter"
[[ -f "$PLAN_DIR/PLAN-053a-caddy-api-route.md" ]] && pass "PLAN-053a" || fail "PLAN-053a"
[[ -f "$PLAN_DIR/PLAN-053b-public-auth-gate.md" ]] && pass "PLAN-053b" || fail "PLAN-053b"
[[ -f "$PLAN_DIR/README.md" ]] && pass "PLAN-053 README" || fail "PLAN-053 README"
[[ -f "$WT" ]] && pass "WT-053" || fail "WT-053"
[[ -f "$ROOT/scripts/deploy-plan-053-api-expose.sh" ]] && pass "deploy script" || fail "deploy script"
[[ -f "$ROOT/scripts/verify-plan-053.sh" ]] && pass "verify script" || fail "verify script"

if [[ -f "$CADDYFILE" ]]; then
  BLOCK="$(awk '/https:\/\/translate\.qyunsgen\.com/,/^}/' "$CADDYFILE")"
  if printf '%s\n' "$BLOCK" | grep -q '/api/v1' \
    && printf '%s\n' "$BLOCK" | grep -q '127.0.0.1:8010'; then
    pass "Caddyfile /api/v1 → 8010"
  else
    fail "Caddyfile missing /api/v1 → 8010"
  fi
else
  fail "Caddyfile missing: $CADDYFILE"
fi

if docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile \
  >"$STAGE_DIR/caddy-validate.log" 2>&1; then
  pass "caddy validate"
else
  fail "caddy validate"
  tail -n 20 "$STAGE_DIR/caddy-validate.log" || true
fi

# --- 公网负向 ---
curl_code() {
  local url="$1"; shift
  curl -sS -o "$STAGE_DIR/body.json" -w '%{http_code}' --max-time 20 "$@" "$url" || echo "000"
}

CODE="$(curl_code "${PUBLIC_BASE}/api/v1/health")"
BODY="$(cat "$STAGE_DIR/body.json" 2>/dev/null || true)"
if [[ "$CODE" == "200" ]] && printf '%s' "$BODY" | grep -q '"schema"' \
  && ! printf '%s' "$BODY" | grep -qE '"env"|"database_url_set"'; then
  pass "public health anonymous (no env leak)"
else
  fail "public health expected 200+schema sans env (got $CODE: $BODY)"
fi

CODE="$(curl_code "${PUBLIC_BASE}/api/v1/projects")"
if [[ "$CODE" == "401" ]]; then
  pass "public projects without Bearer → 401"
else
  fail "public projects expected 401 (got $CODE)"
fi

# production：旁路未开 → OIDC 缺 token 401；旁路误开 → 显式 403。二者均证明 X-Dev 进不去。
CODE="$(curl_code "${PUBLIC_BASE}/api/v1/projects" \
  -H 'X-Dev-User: bypass' -H 'X-Dev-Tenant: bypass')"
if [[ "$CODE" == "403" || "$CODE" == "401" ]]; then
  pass "public projects with X-Dev-* → $CODE (rejected)"
else
  fail "public projects with X-Dev-* expected 401/403 (got $CODE)"
fi

CODE="$(curl_code "${PUBLIC_BASE}/service/meta")"
if [[ "$CODE" == "404" ]]; then
  pass "public /service/meta → 404 (not exposed)"
else
  fail "public /service/meta expected 404 (got $CODE)"
fi

# --- 公网正向 E2E（mint 不可达 → BLOCKED） ---
if [[ -f "$OFFICE_ENV" ]]; then
  # shellcheck disable=SC1090
  set -a
  # 只取 mint secret，避免污染整环境
  MINT_SECRET="$(grep -E '^QYUNSLATION_OIDC_MINT_SECRET=' "$OFFICE_ENV" | head -1 | cut -d= -f2-)"
  set +a
else
  MINT_SECRET="${QYUNSLATION_OIDC_MINT_SECRET:-}"
fi

if [[ -z "${MINT_SECRET:-}" ]]; then
  blocked "OIDC mint secret unset; skip public E2E"
elif ! curl -fsS -o /dev/null --max-time 5 "${OIDC_MINT%/token}/jwks.json" 2>/dev/null \
  && ! curl -fsS -o /dev/null --max-time 5 "http://127.0.0.1:5556/jwks.json" 2>/dev/null; then
  blocked "OIDC pilot :5556 unreachable; skip public E2E"
else
  MINT_RESP="$(curl -sS --max-time 10 -X POST "$OIDC_MINT" \
    -H "X-Mint-Secret: ${MINT_SECRET}" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data 'sub=plan053-verify&tenant=pilot' 2>"$STAGE_DIR/mint.err" || true)"
  TOKEN="$(printf '%s' "$MINT_RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)"
  if [[ -z "$TOKEN" ]]; then
    blocked "mint token failed: ${MINT_RESP:0:200}"
  else
    AUTH=(-H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json')
    SLUG="plan053-$(date +%s)"
    PROJ_BODY="$(curl -sS --max-time 20 -X POST "${PUBLIC_BASE}/api/v1/projects" \
      "${AUTH[@]}" -d "{\"slug\":\"${SLUG}\",\"name\":\"PLAN-053 verify\"}" \
      -w '\n%{http_code}' || true)"
    PROJ_CODE="$(printf '%s' "$PROJ_BODY" | tail -1)"
    PROJ_JSON="$(printf '%s' "$PROJ_BODY" | sed '$d')"
    PROJECT_ID="$(printf '%s' "$PROJ_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or d.get("project",{}).get("id",""))' 2>/dev/null || true)"
    if [[ "$PROJ_CODE" != "200" && "$PROJ_CODE" != "201" ]] || [[ -z "$PROJECT_ID" ]]; then
      # 可能已存在：GET 列表找 slug
      LIST="$(curl -sS --max-time 20 "${PUBLIC_BASE}/api/v1/projects" "${AUTH[@]}" || true)"
      PROJECT_ID="$(printf '%s' "$LIST" | python3 -c "
import json,sys
slug='$SLUG'
data=json.load(sys.stdin)
rows=data if isinstance(data,list) else data.get('items') or data.get('projects') or []
for p in rows:
  if p.get('slug')==slug:
    print(p.get('id','')); break
" 2>/dev/null || true)"
    fi
    if [[ -z "$PROJECT_ID" ]]; then
      fail "E2E create project failed (HTTP $PROJ_CODE): ${PROJ_JSON:0:300}"
    else
      SHA="$(printf 'plan053-e2e' | sha256sum | awk '{print $1}')"
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
          -d "{\"job_id\":\"${JOB_ID}\",\"segments\":[{\"source_text\":\"PLAN-053 E2E source\",\"machine_text\":\"PLAN-053 入队译文\",\"policy\":\"HUMAN_REVIEW\",\"role\":\"body\",\"block_id\":\"b053\"}]}" \
          -w '\n%{http_code}' || true)"
        ENQ_CODE="$(printf '%s' "$ENQ_BODY" | tail -1)"
        ENQ_JSON="$(printf '%s' "$ENQ_BODY" | sed '$d')"
        COUNT="$(printf '%s' "$ENQ_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("count",0))' 2>/dev/null || echo 0)"
        if [[ "$ENQ_CODE" == "200" && "$COUNT" -ge 1 ]]; then
          QCODE="$(curl_code "${PUBLIC_BASE}/api/v1/review/queue?job_id=${JOB_ID}" \
            -H "Authorization: Bearer ${TOKEN}")"
          if [[ "$QCODE" == "200" ]]; then
            pass "public E2E review enqueue+queue (count=$COUNT)"
          else
            fail "E2E queue HTTP $QCODE after enqueue ok"
          fi
        else
          fail "E2E enqueue expected count>=1 (HTTP $ENQ_CODE): ${ENQ_JSON:0:300}"
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
