#!/usr/bin/env bash
# PLAN-005：Word/扫描PDF/图片翻译 + 005e 统一入口
# 用法: bash scripts/deploy-plan-005.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
CADDY_CTR="${QYUNSGEN_CADDY_CONTAINER:-qyunsgen-caddy}"
HOMEPAGE_CTR="${HOMEPAGE_CONTAINER:-qyunsgen-homepage}"

echo "== 安装/更新 qyunslation 可编辑包"
cd "$ROOT"
if [[ -x .venv/bin/qyunslation ]]; then
  echo "qyunslation 已安装，跳过 pip"
else
  uv venv .venv
  uv pip install --python .venv/bin/python -e .
fi


echo "== 同步 systemd units"
mkdir -p ~/.config/systemd/user
cp "$ROOT/scripts/pdf2zh.service" ~/.config/systemd/user/
cp "$ROOT/scripts/qyunslation-office.service" ~/.config/systemd/user/
cp "$ROOT/scripts/office-archive-watch.service" ~/.config/systemd/user/
systemctl --user daemon-reload

echo "== office.env"
if [[ ! -f /home/dev/pdf2zh/office.env ]]; then
  cp "$ROOT/scripts/office.env.example" /home/dev/pdf2zh/office.env
fi
mkdir -p /home/dev/pdf2zh/office_out

echo "== 启动服务"
systemctl --user enable --now qyunslation-office.service
systemctl --user enable --now office-archive-watch.service
systemctl --user enable --now pdf2zh.service

echo "== 等待服务就绪"
for i in $(seq 1 30); do
  curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8010/ && break
  sleep 1
done
for i in $(seq 1 30); do
  curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:7860/ && break
  sleep 1
done

echo "== Caddy reload"
docker exec "$CADDY_CTR" caddy validate --config /etc/caddy/Caddyfile
docker exec "$CADDY_CTR" caddy reload --config /etc/caddy/Caddyfile

echo "== homepage restart"
docker restart "$HOMEPAGE_CTR" >/dev/null

echo "== 验证"
bash "$ROOT/scripts/verify-plan-005.sh" after-d
echo "OK: PLAN-005 已部署（translate.qyunsgen.com 统一入口）"
