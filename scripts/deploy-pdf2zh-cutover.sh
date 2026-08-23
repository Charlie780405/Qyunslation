#!/usr/bin/env bash
# PLAN-002c：将 translate.qyunsgen.com 切到 pdf2zh（7860）
# 用法: bash scripts/deploy-pdf2zh-cutover.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"

echo "== 确保 pdf2zh 已 enable"
systemctl --user enable --now pdf2zh.service
curl -fsS -o /dev/null --max-time 10 http://127.0.0.1:7860/

echo "== 校验 Caddy 已指向 7860"
if ! awk '/https:\/\/translate\.qyunsgen\.com/,/^}/' "$CADDYFILE" | grep -q '127.0.0.1:7860'; then
  echo "FAIL: $CADDYFILE 未反代 7860，请先改 translate 站点块" >&2
  exit 1
fi

echo "== Caddy validate + reload"
docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CTR" caddy reload --config /etc/caddy/Caddyfile

echo "== 冒烟"
bash "$ROOT/scripts/verify-plan-002.sh" after-c
echo "OK: translate.qyunsgen.com → pdf2zh :7860"
