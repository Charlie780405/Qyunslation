#!/usr/bin/env bash
# PLAN-002e：部署 pdf2zh 旁路归档（MinIO translate-docs + watcher）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QYUNSGEN_ROOT="${QYUNSGEN_ROOT:-/home/dev/qyunsgen}"
PDF2ZH_ROOT="${PDF2ZH_ROOT:-/home/dev/pdf2zh}"
ENV_FILE="$PDF2ZH_ROOT/archive.env"
UNIT_SRC="$ROOT/scripts/pdf2zh-archive-watch.service"
UNIT_DST="$HOME/.config/systemd/user/pdf2zh-archive-watch.service"

echo "== 确保 MinIO translate-docs 桶"
if [[ -f "$QYUNSGEN_ROOT/scripts/ensure-minio-buckets.sh" ]]; then
  bash "$QYUNSGEN_ROOT/scripts/ensure-minio-buckets.sh" "$QYUNSGEN_ROOT/.env.docker"
fi

echo "== 安装 minio Python 客户端"
python3 -m pip install --break-system-packages -q minio 2>/dev/null \
  || uv pip install --python "$(command -v python3)" minio

if [[ ! -f "$ENV_FILE" ]]; then
  echo "== 生成 $ENV_FILE"
  AK="$(grep -E '^MINIO_ACCESS_KEY=' "$QYUNSGEN_ROOT/.env.docker" | head -1 | cut -d= -f2- | tr -d '\r')"
  SK="$(grep -E '^MINIO_SECRET_KEY=' "$QYUNSGEN_ROOT/.env.docker" | head -1 | cut -d= -f2- | tr -d '\r')"
  PORT="$(grep -E '^MINIO_API_PORT=' "$QYUNSGEN_ROOT/.env.docker" | head -1 | cut -d= -f2- | tr -d '\r')"
  PORT="${PORT:-9002}"
  cp "$ROOT/scripts/pdf2zh-archive.env.example" "$ENV_FILE"
  sed -i "s/^PDF2ZH_MINIO_ACCESS_KEY=.*/PDF2ZH_MINIO_ACCESS_KEY=$AK/" "$ENV_FILE"
  sed -i "s/^PDF2ZH_MINIO_SECRET_KEY=.*/PDF2ZH_MINIO_SECRET_KEY=$SK/" "$ENV_FILE"
  sed -i "s/^PDF2ZH_MINIO_ENDPOINT=.*/PDF2ZH_MINIO_ENDPOINT=127.0.0.1:$PORT/" "$ENV_FILE"
fi

mkdir -p "$PDF2ZH_ROOT/out" "$PDF2ZH_ROOT/archive"

echo "== 设置 pdf2zh 固定输出目录"
if grep -q '^output = ' "$PDF2ZH_ROOT/config.toml"; then
  sed -i 's|^output = .*|output = "/home/dev/pdf2zh/out"|' "$PDF2ZH_ROOT/config.toml"
fi

echo "== 安装 user systemd unit"
mkdir -p "$HOME/.config/systemd/user"
cp "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable --now pdf2zh-archive-watch.service

echo "== 回填已有 out/ 产物（--once）"
PYTHONPATH="$ROOT" python3 "$ROOT/scripts/pdf2zh-archive-watch.py" --env-file "$ENV_FILE" --once

echo "== 验收"
bash "$ROOT/scripts/verify-plan-002e.sh"
echo "OK: pdf2zh 旁路归档已部署"
