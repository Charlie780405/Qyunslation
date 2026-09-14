#!/usr/bin/env bash
# PLAN-053a：将 translate.qyunsgen.com /api/v1/* 切到 sidecar :8010
# 用法: bash scripts/deploy-plan-053-api-expose.sh
# 回滚: 还原 Caddyfile.bak-053-* 后 docker exec qyunsgen-caddy caddy reload --config /etc/caddy/Caddyfile
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDYFILE="$QYUNSGEN_ROOT/config/Caddyfile-production-public"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"
PUBLIC_BASE="${QYUNSLATION_PUBLIC_BASE:-https://translate.qyunsgen.com}"

echo "== 确保 sidecar :8010 在听"
systemctl --user is-active --quiet qyunslation-office.service \
  || systemctl --user start qyunslation-office.service
curl -fsS -o /dev/null --max-time 10 http://127.0.0.1:8010/api/v1/health

echo "== 备份 Caddyfile（若尚无 bak-053）"
if ! ls "$QYUNSGEN_ROOT/config"/Caddyfile-production-public.bak-053-* >/dev/null 2>&1; then
  TS="$(date +%Y%m%d%H%M%S)"
  cp -a "$CADDYFILE" "$QYUNSGEN_ROOT/config/Caddyfile-production-public.bak-053-${TS}"
  echo "备份 → Caddyfile-production-public.bak-053-${TS}"
fi

echo "== 校验 translate 块含 /api/v1 → 8010"
BLOCK="$(awk '/https:\/\/translate\.qyunsgen\.com/,/^}/' "$CADDYFILE")"
if ! printf '%s\n' "$BLOCK" | grep -q '@qy_api'; then
  echo "FAIL: 缺少 @qy_api matcher" >&2
  exit 1
fi
if ! printf '%s\n' "$BLOCK" | grep -q '/api/v1'; then
  echo "FAIL: 缺少 /api/v1 path" >&2
  exit 1
fi
if ! printf '%s\n' "$BLOCK" | grep -q '127.0.0.1:8010'; then
  echo "FAIL: 未反代 127.0.0.1:8010" >&2
  exit 1
fi
# 兜底仍须指向 7860
if ! printf '%s\n' "$BLOCK" | grep -q '127.0.0.1:7860'; then
  echo "FAIL: translate 兜底丢失 7860" >&2
  exit 1
fi

echo "== Caddy validate + reload"
docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CTR" caddy reload --config /etc/caddy/Caddyfile

echo "== 冒烟：公网 /api/v1/health"
CODE="$(curl -sS -o /tmp/plan053-health.json -w '%{http_code}' --max-time 20 \
  "${PUBLIC_BASE}/api/v1/health" || true)"
if [[ "$CODE" != "200" ]]; then
  echo "FAIL: 公网 health HTTP $CODE（期望 200）" >&2
  cat /tmp/plan053-health.json 2>/dev/null || true
  exit 1
fi
echo "OK: ${PUBLIC_BASE}/api/v1/health → 200"
cat /tmp/plan053-health.json
echo
echo "OK: translate.qyunsgen.com /api/v1 → sidecar :8010"
echo "回滚: 还原 bak-053-* 后 docker exec $CADDY_CTR caddy reload --config /etc/caddy/Caddyfile"
