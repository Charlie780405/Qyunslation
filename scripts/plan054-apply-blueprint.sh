#!/usr/bin/env bash
# PLAN-054b：幂等落地 qyunslation OIDC（优先 API；blueprint 文件作 SSOT 文档）
# 用法: bash scripts/plan054-apply-blueprint.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AK_DIR="$ROOT/deploy/authentik"
ENV_FILE="$AK_DIR/.env"
AK_URL="${AUTHENTIK_API_URL:-http://127.0.0.1:9000}"

[[ -f "$ENV_FILE" ]] || { echo "FAIL: missing $ENV_FILE — run deploy-plan-054-authentik.sh first" >&2; exit 1; }

BOOT_TOKEN="$(grep -E '^AUTHENTIK_BOOTSTRAP_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
CLIENT_SECRET="$(grep -E '^QYUNSLATION_OIDC_CLIENT_SECRET=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
[[ -n "$BOOT_TOKEN" && -n "$CLIENT_SECRET" ]] || { echo "FAIL: bootstrap/client secret empty" >&2; exit 1; }
AUTH_H=("Authorization: Bearer ${BOOT_TOKEN}" "Content-Type: application/json")
REDIRECT_URI="${QYUNSLATION_OIDC_REDIRECT_URI:-https://translate.qyunsgen.com/auth/callback}"

echo "== 等待 Authentik ready"
for _ in $(seq 1 40); do
  curl -fsS -o /dev/null --max-time 5 "$AK_URL/-/health/ready/" 2>/dev/null && break
  sleep 3
done

api_get() { curl -fsS --max-time 20 -H "Authorization: Bearer ${BOOT_TOKEN}" "$1"; }
api_json() { curl -sS --max-time 30 -H "${AUTH_H[0]}" -H "${AUTH_H[1]}" "$@"; }

echo "== 解析 flows / cert / scopes"
AUTH_FLOW="$(api_get "$AK_URL/api/v3/flows/instances/default-provider-authorization-implicit-consent/" | python3 -c 'import json,sys; print(json.load(sys.stdin)["pk"])')"
INV_FLOW="$(api_get "$AK_URL/api/v3/flows/instances/default-provider-invalidation-flow/" | python3 -c 'import json,sys; print(json.load(sys.stdin)["pk"])')"
CERT="$(api_get "$AK_URL/api/v3/crypto/certificatekeypairs/" | python3 -c 'import json,sys; print(json.load(sys.stdin)["results"][0]["pk"])')"

# tenant scope（幂等）
SCOPE_PK="$(api_get "$AK_URL/api/v3/propertymappings/provider/scope/?search=tenant" | python3 -c '
import json,sys
for x in json.load(sys.stdin).get("results",[]):
  if x.get("scope_name")=="tenant" or x.get("managed")=="goauthentik.io/qyunslation/scope-tenant":
    print(x["pk"]); break
' || true)"
if [[ -z "$SCOPE_PK" ]]; then
  SCOPE_PK="$(api_json -X POST "$AK_URL/api/v3/propertymappings/provider/scope/" -d "$(python3 - <<'PY'
import json
print(json.dumps({
  "name": "qyunslation OAuth Mapping: tenant",
  "scope_name": "tenant",
  "description": "Tenant slug for qyunslation IdentityContext",
  "expression": "return {\n    \"tenant\": request.user.attributes.get(\"tenant\", \"pilot\"),\n}",
  "managed": "goauthentik.io/qyunslation/scope-tenant",
}))
PY
)" | python3 -c 'import json,sys; print(json.load(sys.stdin)["pk"])')"
fi
echo "SCOPE_PK=$SCOPE_PK AUTH_FLOW=$AUTH_FLOW CERT=$CERT"

# workbench capability scope（幂等）：仅由 Authentik 试点组授予，浏览器不能伪造。
ROLES_SCOPE_PK="$(api_get "$AK_URL/api/v3/propertymappings/provider/scope/?search=roles" | python3 -c '
import json,sys
for x in json.load(sys.stdin).get("results",[]):
  if x.get("scope_name")=="roles" and x.get("managed")=="goauthentik.io/qyunslation/scope-roles":
    print(x["pk"]); break
' || true)"
if [[ -z "$ROLES_SCOPE_PK" ]]; then
  ROLES_SCOPE_PK="$(api_json -X POST "$AK_URL/api/v3/propertymappings/provider/scope/" -d "$(python3 - <<'PY'
import json
print(json.dumps({
  "name": "qyunslation OAuth Mapping: roles",
  "scope_name": "roles",
  "description": "Server-side roles and Vue workbench capability",
  "expression": "roles = request.user.attributes.get('roles', [])\nif isinstance(roles, str):\n    roles = [roles]\nelse:\n    roles = list(roles or [])\nif request.user.ak_groups.filter(name='qyunslation-vue-beta').exists():\n    roles.append('workbench_v2')\nreturn {'roles': sorted(set(str(item).strip() for item in roles if str(item).strip()))}",
  "managed": "goauthentik.io/qyunslation/scope-roles",
}))
PY
)" | python3 -c 'import json,sys; print(json.load(sys.stdin)["pk"])')"
fi
echo "ROLES_SCOPE_PK=$ROLES_SCOPE_PK"

MAPS="$(api_get "$AK_URL/api/v3/propertymappings/provider/scope/?page_size=50" | python3 -c '
import json,sys
want={"openid","email","profile","tenant","roles"}
ids=[]
for x in json.load(sys.stdin)["results"]:
  if x.get("scope_name") in want:
    ids.append(x["pk"])
print(json.dumps(ids))
')"

PROV_PK="$(api_get "$AK_URL/api/v3/providers/oauth2/?search=qyunslation" | python3 -c '
import json,sys
for x in json.load(sys.stdin).get("results",[]):
  if x.get("name")=="qyunslation" or x.get("client_id")=="qyunslation":
    print(x["pk"]); break
' || true)"

PROV_BODY="$(MAPS="$MAPS" AUTH_FLOW="$AUTH_FLOW" INV_FLOW="$INV_FLOW" CERT="$CERT" CLIENT_SECRET="$CLIENT_SECRET" REDIRECT_URI="$REDIRECT_URI" python3 - <<'PY'
import json, os
print(json.dumps({
  "name": "qyunslation",
  "authorization_flow": os.environ["AUTH_FLOW"],
  "invalidation_flow": os.environ["INV_FLOW"],
  "client_type": "confidential",
  "client_id": "qyunslation",
  "client_secret": os.environ["CLIENT_SECRET"],
  "redirect_uris": [{"url": os.environ["REDIRECT_URI"], "matching_mode": "strict"}],
  "access_code_validity": "minutes=1",
  "access_token_validity": "hours=1",
  "refresh_token_validity": "days=30",
  "include_claims_in_id_token": True,
  "signing_key": os.environ["CERT"],
  "sub_mode": "hashed_user_id",
  "issuer_mode": "per_provider",
  "property_mappings": json.loads(os.environ["MAPS"]),
}))
PY
)"

if [[ -z "$PROV_PK" ]]; then
  PROV_PK="$(api_json -X POST "$AK_URL/api/v3/providers/oauth2/" -d "$PROV_BODY" | python3 -c 'import json,sys; print(json.load(sys.stdin)["pk"])')"
  echo "created provider pk=$PROV_PK"
else
  api_json -X PATCH "$AK_URL/api/v3/providers/oauth2/${PROV_PK}/" -d "$PROV_BODY" >/dev/null
  echo "updated provider pk=$PROV_PK"
fi

APP_SLUG="$(api_get "$AK_URL/api/v3/core/applications/?search=qyunslation" | python3 -c '
import json,sys
for x in json.load(sys.stdin).get("results",[]):
  if x.get("slug")=="qyunslation":
    print(x["slug"]); break
' || true)"
APP_BODY="$(python3 -c "import json; print(json.dumps({'name':'qyunslation','slug':'qyunslation','provider': int('$PROV_PK') if str('$PROV_PK').isdigit() else '$PROV_PK','meta_launch_url':'https://translate.qyunsgen.com/api/v1/health','policy_engine_mode':'any'}))")"
if [[ -z "$APP_SLUG" ]]; then
  api_json -X POST "$AK_URL/api/v3/core/applications/" -d "$APP_BODY" >/dev/null
  echo "created application qyunslation"
else
  api_json -X PATCH "$AK_URL/api/v3/core/applications/qyunslation/" -d "$APP_BODY" >/dev/null
  echo "updated application qyunslation"
fi

echo "== discovery + M2M"
DISC="$(curl -fsS --max-time 15 -H 'Host: auth.qyunsgen.com' -H 'X-Forwarded-Proto: https' \
  "$AK_URL/application/o/qyunslation/.well-known/openid-configuration")"
echo "$DISC" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("issuer:", d.get("issuer")); print("jwks:", d.get("jwks_uri"))'

RESP="$(curl -fsS --max-time 20 -X POST "$AK_URL/application/o/token/" \
  -H 'Host: auth.qyunsgen.com' -H 'X-Forwarded-Proto: https' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'client_id=qyunslation' \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode 'scope=openid profile email tenant')"
export PLAN054_TOKEN_RESP="$RESP"
python3 - <<'PY'
import json, os, base64, sys
d = json.loads(os.environ["PLAN054_TOKEN_RESP"])
tok = d.get("access_token") or ""
if not tok:
    print("FAIL:", os.environ["PLAN054_TOKEN_RESP"][:400]); sys.exit(1)
pad = "=" * ((4 - len(tok.split(".")[1]) % 4) % 4)
payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + pad))
print("iss:", payload.get("iss"))
print("aud:", payload.get("aud"))
print("tenant:", payload.get("tenant"))
assert payload.get("aud") == "qyunslation"
assert payload.get("tenant")
assert str(payload.get("iss") or "").startswith("https://auth.qyunsgen.com/")
print("OK: M2M JWT")
PY

echo "OK: PLAN-054b OIDC 契约就绪"
