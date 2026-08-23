#!/usr/bin/env bash
# deploy-taizhou-ollama-003b.sh — 按 baseline-003b 设置泰州 Ollama 调度
# 用法: bash scripts/deploy-taizhou-ollama-003b.sh [NUM_PARALLEL]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASELINE="${ROOT}/docs/perf/baseline-003b.json"
SSH_TARGET="${TAIZHOU_SSH:-genscend@100.67.66.123}"

if [[ -f "$BASELINE" ]]; then
  NUM_PARALLEL="${1:-$(python3 -c "import json; print(json.load(open('$BASELINE'))['recommended_ollama_num_parallel'])")}"
else
  NUM_PARALLEL="${1:-2}"
fi

echo "泰州 Ollama: OLLAMA_NUM_PARALLEL=${NUM_PARALLEL} (KEEP_ALIVE 已在 system override)"

ssh "$SSH_TARGET" bash -s -- "$NUM_PARALLEL" <<'REMOTE'
set -euo pipefail
NUM_PARALLEL="$1"
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
if grep -q '^Environment=OLLAMA_NUM_PARALLEL=' "$OVERRIDE" 2>/dev/null; then
  sudo sed -i "s/^Environment=OLLAMA_NUM_PARALLEL=.*/Environment=OLLAMA_NUM_PARALLEL=${NUM_PARALLEL}/" "$OVERRIDE"
else
  echo "Environment=OLLAMA_NUM_PARALLEL=${NUM_PARALLEL}" | sudo tee -a "$OVERRIDE" >/dev/null
fi
sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 4
curl -fsS --max-time 8 http://127.0.0.1:11434/api/tags | head -c 200
echo
curl -fsS --max-time 5 http://127.0.0.1:8120/health || true
REMOTE

echo "done: NUM_PARALLEL=${NUM_PARALLEL}"
