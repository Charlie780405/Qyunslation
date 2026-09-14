#!/usr/bin/env bash
# PLAN-054a：启动 Authentik + 写入 Caddy auth 站点 + reload
# 用法: bash scripts/deploy-plan-054-authentik.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AK_DIR="$ROOT/deploy/authentik"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"

cd "$AK_DIR"

if [[ ! -f .env ]]; then
  echo "== 生成 deploy/authentik/.env（首次）"
  PG_PASS="$(openssl rand -base64 36 | tr -d '\n')"
  SECRET="$(openssl rand -base64 60 | tr -d '\n')"
  BOOT_TOKEN="$(openssl rand -base64 32 | tr -d '\n')"
  BOOT_PASS="$(openssl rand -base64 18 | tr -d '\n')"
  CLIENT_SECRET="$(openssl rand -base64 32 | tr -d '\n')"
  cat >.env <<EOF
PG_USER=authentik
PG_DB=authentik
PG_PASS=${PG_PASS}
AUTHENTIK_SECRET_KEY=${SECRET}
AUTHENTIK_BOOTSTRAP_EMAIL=admin@qyunsgen.com
AUTHENTIK_BOOTSTRAP_PASSWORD=${BOOT_PASS}
AUTHENTIK_BOOTSTRAP_TOKEN=${BOOT_TOKEN}
AUTHENTIK_HOST=https://auth.qyunsgen.com/
QYUNSLATION_OIDC_CLIENT_ID=qyunslation
QYUNSLATION_OIDC_CLIENT_SECRET=${CLIENT_SECRET}
AUTHENTIK_TAG=2025.10.4
COMPOSE_PORT_HTTP=9000
EOF
  chmod 600 .env
  echo "已写入 $AK_DIR/.env（含 bootstrap 密码，勿入库）"
else
  echo "== 复用已有 deploy/authentik/.env"
fi

echo "== 校验 Caddyfile 含 auth.qyunsgen.com → 9000"
if ! awk '/https:\/\/auth\.qyunsgen\.com/,/^}/' "$CADDYFILE" | grep -q '127.0.0.1:9000'; then
  echo "FAIL: $CADDYFILE 缺少 auth → 9000 块" >&2
  exit 1
fi

echo "== docker compose pull + up"
docker compose pull
docker compose up -d

echo "== 等待 Authentik live"
ok=0
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null --max-time 5 http://127.0.0.1:9000/-/health/live/ 2>/dev/null; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "$ok" != "1" ]]; then
  echo "FAIL: Authentik /- /health/live/ 未就绪" >&2
  docker compose ps || true
  docker compose logs --tail 40 server || true
  exit 1
fi
echo "OK: http://127.0.0.1:9000/-/health/live/"

echo "== Caddy validate + reload"
docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CTR" caddy reload --config /etc/caddy/Caddyfile

echo "== 冒烟：经 Caddy --resolve 打 auth"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 \
  --resolve auth.qyunsgen.com:443:127.0.0.1 \
  https://auth.qyunsgen.com/-/health/live/ || true)"
if [[ "$CODE" != "200" && "$CODE" != "204" ]]; then
  echo "WARN: Caddy local resolve health HTTP $CODE（继续；公网 DNS 可能另议）"
else
  echo "OK: Caddy → Authentik health HTTP $CODE"
fi

echo "OK: PLAN-054a Authentik 已部署"
echo "下一步: bash scripts/plan054-apply-blueprint.sh"
