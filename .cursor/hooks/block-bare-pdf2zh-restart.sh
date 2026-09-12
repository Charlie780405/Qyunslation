#!/usr/bin/env bash
# PLAN-047g / SK-Q004：拦截裸重启 pdf2zh，强制走双服务部署脚本。
set -euo pipefail
input="$(cat || true)"
# fail open if no jq / empty
cmd="$(printf '%s' "$input" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    d={}
print(d.get("command") or d.get("tool_input",{}).get("command") or "")
' 2>/dev/null || true)"

if printf '%s' "$cmd" | grep -Eq 'systemctl[[:space:]]+--user[[:space:]]+restart[[:space:]]+pdf2zh\.service([[:space:]]|$)'; then
  if ! printf '%s' "$cmd" | grep -Eq 'qyunslation-office\.service|deploy-translate-stack\.sh'; then
    printf '%s\n' '{"permission":"deny","user_message":"禁止裸重启 pdf2zh.service。请改用: bash scripts/deploy-translate-stack.sh（同时重启 pdf2zh + qyunslation-office，并核对指纹）。"}'
    exit 0
  fi
fi
printf '%s\n' '{"permission":"allow"}'
