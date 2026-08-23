#!/usr/bin/env bash
# deploy-taizhou-ollama-004a.sh — PLAN-004a：强制 Ollama ctx + 记录 llama-server
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_TARGET="${TAIZHOU_SSH:-genscend@100.67.66.123}"
NUM_CTX="${OLLAMA_NUM_CTX:-8192}"
NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-4}"

echo "泰州 Ollama 004a: NUM_CTX=${NUM_CTX} NUM_PARALLEL=${NUM_PARALLEL}"

OBSERVED_JSON="$(ssh "$SSH_TARGET" bash -s -- "$NUM_CTX" "$NUM_PARALLEL" <<'REMOTE'
set -euo pipefail
NUM_CTX="$1"
NUM_PARALLEL="$2"
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
sudo mkdir -p "$(dirname "$OVERRIDE")"

upsert_env() {
  local key="$1" val="$2"
  if grep -q "^Environment=${key}=" "$OVERRIDE" 2>/dev/null; then
    sudo sed -i "s|^Environment=${key}=.*|Environment=${key}=${val}|" "$OVERRIDE"
  else
    echo "Environment=${key}=${val}" | sudo tee -a "$OVERRIDE" >/dev/null
  fi
}

upsert_env OLLAMA_NUM_CTX "$NUM_CTX"
upsert_env OLLAMA_NUM_PARALLEL "$NUM_PARALLEL"
upsert_env OLLAMA_KEEP_ALIVE -1

sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 6

curl -fsS --max-time 120 http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen3.6:35b-a3b","prompt":"ping","stream":false,"options":{"num_predict":8}}' \
  >/dev/null || true

# PLAN-004a: Modelfile num_ctx 覆盖模型默认 262144
ollama show qwen3.6:35b-a3b --modelfile > /tmp/qwen35-modelfile || true
if [[ -f /tmp/qwen35-modelfile ]] && ! grep -q '^PARAMETER num_ctx' /tmp/qwen35-modelfile; then
  echo "PARAMETER num_ctx ${NUM_CTX}" >> /tmp/qwen35-modelfile
  ollama create qwen3.6:35b-a3b -f /tmp/qwen35-modelfile
fi
sleep 2
curl -fsS --max-time 120 http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"qwen3.6:35b-a3b\",\"prompt\":\"ping\",\"stream\":false,\"options\":{\"num_predict\":8}}" \
  >/dev/null || true
sleep 2

ps aux | grep '[l]lama-server' || true
curl -fsS --max-time 5 http://127.0.0.1:8120/health || echo "HPD: unavailable"
REMOTE
)"

echo "$OBSERVED_JSON"

# Parse llama-server lines into JSON array
python3 - "$ROOT" "$OBSERVED_JSON" <<'PY'
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
raw = sys.argv[2]
lines = [ln.strip() for ln in raw.splitlines() if "llama-server" in ln]
entries = []
for ln in lines:
    c = re.search(r"\s-c\s+(\d+)", ln)
    np = re.search(r"\s-np\s+(\d+)", ln)
    entries.append({
        "line": ln[:500],
        "ctx": int(c.group(1)) if c else None,
        "num_parallel": int(np.group(1)) if np else None,
    })

out = root / "docs/perf/observed-llama-004a.json"
out.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "observed_llama_server": entries,
}
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out}")
PY

echo "done: deploy-taizhou-ollama-004a"
