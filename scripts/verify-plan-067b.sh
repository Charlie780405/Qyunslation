#!/usr/bin/env bash
# PLAN-067b：Authentik provider、DNS、Caddy issuer 前置门禁
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AK_URL="${AUTHENTIK_API_URL:-http://127.0.0.1:9000}"
AUTH_PUBLIC="${QYUNSLATION_AUTH_PUBLIC:-https://auth.qyunsgen.com}"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
trap 'rm -rf -- "$STAGE_DIR"' EXIT
cd "$ROOT" || exit 1

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

grep -q 'QYUNSLATION_OIDC_REDIRECT_URI:-https://translate.qyunsgen.com/auth/callback' \
  scripts/plan054-apply-blueprint.sh \
  && pass 'apply script defaults to /auth/callback' \
  || fail 'apply script callback default drifted'

if curl -fsS --max-time 8 -o /dev/null "$AK_URL/-/health/ready/"; then
  pass 'local Authentik ready'
else
  fail 'local Authentik unavailable'
fi

AK_ENV="$ROOT/deploy/authentik/.env"
if [[ -f "$AK_ENV" ]]; then
  BOOT_TOKEN="$(grep -E '^AUTHENTIK_BOOTSTRAP_TOKEN=' "$AK_ENV" | head -1 | cut -d= -f2-)"
  if [[ -n "$BOOT_TOKEN" ]]; then
    if curl -fsS --max-time 15 -H "Authorization: Bearer ${BOOT_TOKEN}" \
      "$AK_URL/api/v3/providers/oauth2/?search=qyunslation" >"$STAGE_DIR/provider.json"; then
      python3 - "$STAGE_DIR/provider.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
items = [x for x in data.get("results", []) if x.get("name") == "qyunslation"]
assert len(items) == 1, "expected exactly one qyunslation provider"
provider = items[0]
redirects = provider.get("redirect_uris") or []
assert redirects == [{"matching_mode": "strict", "url": "https://translate.qyunsgen.com/auth/callback"}], redirects
assert provider.get("client_id") == "qyunslation", provider.get("client_id")
print("provider callback/client_id: PASS")
PY
      [[ $? -eq 0 ]] && pass 'provider callback and client id' || fail 'provider callback/client id mismatch'
    else
      fail 'provider API query failed'
    fi

    if curl -fsS --max-time 15 -H "Authorization: Bearer ${BOOT_TOKEN}" \
      "$AK_URL/api/v3/core/groups/?search=qyunslation-vue-beta&page_size=20" >"$STAGE_DIR/group.json"; then
      python3 - "$STAGE_DIR/group.json" <<'PY'
import json, sys
items = [x for x in json.load(open(sys.argv[1], encoding="utf-8")).get("results", [])
         if x.get("name") == "qyunslation-vue-beta"]
assert len(items) == 1
assert items[0].get("is_superuser") is False
print("beta group: PASS")
PY
      [[ $? -eq 0 ]] && pass 'beta group exists and is non-superuser' || fail 'beta group invalid'
    else
      fail 'beta group API query failed'
    fi
  else
    fail 'Authentik bootstrap token missing'
  fi
else
  fail 'deploy/authentik/.env missing'
fi

if [[ -f "$CADDYFILE" ]] && rg -q 'https://auth\.qyunsgen\.com' "$CADDYFILE" \
  && rg -q 'reverse_proxy 127\.0\.0\.1:9000' "$CADDYFILE"; then
  pass 'qyunsgen Caddy auth site present'
else
  fail 'qyunsgen Caddy auth site missing'
fi

if docker exec qyunsgen-caddy caddy validate --config /etc/caddy/Caddyfile \
  >"$STAGE_DIR/caddy.log" 2>&1; then
  pass 'Caddy configuration valid'
else
  fail 'Caddy configuration invalid'
fi

LOCAL_CODE="$(curl -skS --max-time 12 --resolve auth.qyunsgen.com:443:127.0.0.1 \
  -o "$STAGE_DIR/local-health" -w '%{http_code}' \
  "$AUTH_PUBLIC/-/health/live/" 2>/dev/null || true)"
if [[ "$LOCAL_CODE" == "200" ]]; then
  pass 'Caddy local-resolve Authentik health 200'
else
  fail "Caddy local-resolve Authentik health HTTP $LOCAL_CODE"
fi

if getent ahosts auth.qyunsgen.com >"$STAGE_DIR/dns" 2>/dev/null; then
  pass 'auth.qyunsgen.com host DNS resolves'
  PUB_CODE="$(curl -sS --max-time 15 -o "$STAGE_DIR/public-jwks" -w '%{http_code}' \
    "$AUTH_PUBLIC/application/o/qyunslation/jwks/" 2>/dev/null || true)"
  if [[ "$PUB_CODE" == "200" ]] && grep -q '"keys"' "$STAGE_DIR/public-jwks"; then
    pass 'public JWKS 200 with keys'
  else
    fail "public JWKS expected 200 with keys, got HTTP $PUB_CODE"
  fi
else
  blocked 'auth.qyunsgen.com DNS unresolved; add the public DNS record before 067c'
fi

if [[ "$FAILURES" -gt 0 ]]; then
  printf 'SUMMARY: FAIL fail=%s blocked=%s\n' "$FAILURES" "$BLOCKED"
  exit 1
fi
if [[ "$BLOCKED" -gt 0 ]]; then
  printf 'SUMMARY: BLOCKED blocked=%s fail=0\n' "$BLOCKED"
  exit 2
fi
printf 'SUMMARY: PASS fail=0 blocked=0\n'
