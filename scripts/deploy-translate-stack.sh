#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-047a：同时重启 pdf2zh + qyunslation-office，并核对 sidecar 代码指纹。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIDECAR_URL="${QYUNSLATION_OFFICE_URL:-http://127.0.0.1:8010}"
IMG="$ROOT/qyunslation/extensions/image_translate.py"

echo "== restart pdf2zh.service + qyunslation-office.service =="
systemctl --user restart pdf2zh.service qyunslation-office.service

echo "== wait for sidecar health =="
ok=0
for i in $(seq 1 40); do
  if curl -sf "$SIDECAR_URL/service/image-translate-health" >/tmp/qy-sidecar-health.json 2>/dev/null; then
    ok=1
    break
  fi
  sleep 0.5
done
if [[ "$ok" != "1" ]]; then
  echo "FAIL: sidecar health endpoint not ready"
  systemctl --user --no-pager --full status qyunslation-office.service | tail -n 30 || true
  exit 1
fi

LOCAL_FP="$(python3 - <<PY
import hashlib
from pathlib import Path
p = Path("$IMG")
print(hashlib.sha256(p.read_bytes()).hexdigest()[:12])
PY
)"
REMOTE_FP="$(python3 - <<'PY'
import json
j=json.load(open("/tmp/qy-sidecar-health.json"))
print(j.get("code_fingerprint") or "")
PY
)"

echo "local  fingerprint: $LOCAL_FP"
echo "remote fingerprint: $REMOTE_FP"
python3 - <<'PY'
import json
j=json.load(open("/tmp/qy-sidecar-health.json"))
caps = j.get("capabilities") or {}
print("capabilities:", {k: caps.get(k) for k in (
    "has_rotated_tier", "figure_tier_max_px", "has_ocr_garbage_filter",
    "figure_tier_min_px", "tier_k_floor")})
PY

if [[ "$LOCAL_FP" != "$REMOTE_FP" ]]; then
  echo "FAIL: fingerprint mismatch — sidecar still running old code"
  exit 1
fi

echo "PASS: translate stack deployed; fingerprints match"
systemctl --user is-active pdf2zh.service qyunslation-office.service
