#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-047a：同时重启 pdf2zh + qyunslation-office，并核对 sidecar 代码指纹。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIDECAR_URL="${QYUNSLATION_OFFICE_URL:-http://127.0.0.1:8010}"
IMG="$ROOT/qyunslation/extensions/image_translate.py"
OFFICE_ENV="${QYUNSLATION_OFFICE_ENV:-/home/dev/pdf2zh/office.env}"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
GATE="$ROOT/scripts/deploy_gate.py"

if [[ -f "$OFFICE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^(QYUNSLATION_DATABASE_URL|QYUNSLATION_OFFICE_URL)=' "$OFFICE_ENV" | sed 's/^/export /')
  set +a
fi

echo "== PLAN-075b deploy gates (pre) =="
if [[ -f "$GATE" && -x "$PY" ]]; then
  "$PY" "$GATE" pre --base-url "$SIDECAR_URL" || {
    echo "FAIL: pre-deploy gate blocked restart; fix migration/frontend then retry"
    exit 1
  }
  echo "deploy git commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
else
  echo "WARN: deploy_gate.py or Python missing; skipping pre-deploy checks"
fi
if [[ -z "${QYUNSLATION_API_TOKEN:-}${DOCUTRANSLATE_API_TOKEN:-}${API_TOKEN:-}" && -f "$OFFICE_ENV" ]]; then
  QYUNSLATION_API_TOKEN="$(python3 - <<PY
from pathlib import Path
wanted = ("QYUNSLATION_API_TOKEN", "DOCUTRANSLATE_API_TOKEN", "API_TOKEN")
for line in Path("$OFFICE_ENV").read_text(encoding="utf-8").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    if key in wanted and value.strip():
        print(value.strip().strip("\"'"))
        break
PY
)"
  export QYUNSLATION_API_TOKEN
fi

echo "== restart pdf2zh.service + qyunslation-office.service =="
systemctl --user restart pdf2zh.service qyunslation-office.service

echo "== wait for sidecar health =="
ok=0
for i in $(seq 1 40); do
  health_headers=()
  if [[ -n "${QYUNSLATION_API_TOKEN:-}${DOCUTRANSLATE_API_TOKEN:-}${API_TOKEN:-}" ]]; then
    health_headers=(-H "Authorization: Bearer ${QYUNSLATION_API_TOKEN:-${DOCUTRANSLATE_API_TOKEN:-${API_TOKEN:-}}}")
  fi
  if curl -sf "${health_headers[@]}" "$SIDECAR_URL/service/image-translate-health" >/tmp/qy-sidecar-health.json 2>/dev/null; then
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

echo "== PLAN-075b deploy gates (post) =="
if [[ -f "$GATE" && -x "$PY" ]]; then
  "$PY" "$GATE" post --base-url "$SIDECAR_URL" || {
    echo "FAIL: post-deploy API route probe failed; backend may be stale"
    exit 1
  }
fi

systemctl --user is-active pdf2zh.service qyunslation-office.service
