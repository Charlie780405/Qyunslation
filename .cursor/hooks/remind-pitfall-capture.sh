#!/usr/bin/env bash
# PLAN-047g / SK-Q008：会话结束若改过核心目录且 inbox 有待归档，提醒沉淀。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INBOX="$ROOT/.cursor/skills/skill-registry/pitfalls-inbox.md"
msg=""
if [[ -f "$INBOX" ]] && grep -q 'status: 待归档' "$INBOX"; then
  msg="pitfalls-inbox.md 仍有待归档条目。请运行: python3 scripts/skill-pitfall-capture.py --promote <SIG> --skill <SK-ID>"
fi
# stop hooks：输出 followup_message（若 schema 支持）；否则 stdout 即可
if [[ -n "$msg" ]]; then
  python3 - <<PY
import json
print(json.dumps({"followup_message": """$msg"""}))
PY
else
  echo '{}'
fi
