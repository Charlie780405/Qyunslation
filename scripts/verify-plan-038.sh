#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-038 gap registry consistency gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
REGISTRY="$ROOT/docs/plans/PLAN-038-gap-closure/registry.md"
FAILURES=0

cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }

[[ -f "$REGISTRY" ]] || { printf 'SUMMARY: FAIL blocked=1 missing registry\n'; exit 1; }
[[ -f "$ROOT/docs/plans/PLAN-038-gap-closure/PLAN-038-gap-closure.md" ]] || {
  fail "missing PLAN-038 charter"; printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"; exit 1
}

# Required G-IDs from charter inventory
REQUIRED_IDS=(
  G-DOC-001 G-DOC-002 G-DOC-003 G-DOC-004 G-DOC-005 G-DOC-006 G-DOC-007 G-DOC-008
  G-DOC-009 G-DOC-010 G-DOC-011 G-DOC-012 G-DOC-013 G-DOC-014
  G-OPS-001 G-OPS-002 G-OPS-003 G-OPS-004 G-OPS-006
  G-CAP-001 G-CAP-002 G-CAP-003 G-CAP-004 G-CAP-005 G-CAP-006 G-CAP-007 G-CAP-008 G-CAP-009 G-CAP-011
  G-WONT-001 G-WONT-002 G-WONT-003 G-WONT-004 G-WONT-005 G-WONT-006 G-WONT-007 G-WONT-008
)

missing=0
for id in "${REQUIRED_IDS[@]}"; do
  if ! grep -q "| ${id} |" "$REGISTRY"; then
    fail "registry missing $id"
    missing=1
  fi
done
[[ "$missing" -eq 0 ]] && pass "registry has all required G-IDs"

# Parse closed rows: if source still claims stale open status for synced docs
check_closed_doc_sync() {
  local id="$1" bad_pattern="$2" file="$3"
  local status
  status="$(awk -F'|' -v id="$id" '$2 ~ id { gsub(/ /,"",$5); print $5; exit }' "$REGISTRY")"
  if [[ "$status" != "closed" ]]; then
    return 0
  fi
  if [[ -f "$file" ]] && grep -Eq "$bad_pattern" "$file"; then
    fail "$id closed but $file still matches /$bad_pattern/"
  fi
}

check_closed_doc_sync G-DOC-001 '状态：\*\*实施中\*\*' \
  "$ROOT/docs/plans/PLAN-035-table-execution-fidelity/PLAN-035a-digit-token-policy.md"
check_closed_doc_sync G-DOC-005 '状态：\*\*待批准\*\*' \
  "$ROOT/docs/plans/PLAN-036-table-policy-unification/PLAN-036a-policy-ssot-refactor.md"
check_closed_doc_sync G-DOC-007 '030 未关' \
  "$ROOT/docs/walkthroughs/WT-033n-head-evidence-rebind.md"
check_closed_doc_sync G-DOC-011 '状态：执行中' \
  "$ROOT/docs/plans/PLAN-001-delivery-gpu-audit/PLAN-001-delivery-gpu-audit.md"
check_closed_doc_sync G-DOC-013 '状态：\*\*已批准，实施中\*\*' \
  "$ROOT/docs/plans/PLAN-030-semantic-layout-translation/PLAN-030d-manifest-ssot-execution-parity.md"

# open gaps (except 038g + INFO) must have owning subplan file
while IFS='|' read -r _ gid _ owner status _; do
  gid="$(echo "$gid" | xargs)"
  owner="$(echo "$owner" | xargs)"
  status="$(echo "$status" | xargs)"
  [[ "$gid" == G-* ]] || continue
  [[ "$status" == "open" ]] || continue
  case "$owner" in
    038g) continue ;;  # deferred polish
  esac
  # INFO may stay open
  sev="$(awk -F'|' -v id="$gid" '$2 ~ id { gsub(/ /,"",$3); print $3; exit }' "$REGISTRY")"
  [[ "$sev" == "INFO" ]] && continue
  sub="$ROOT/docs/plans/PLAN-038-gap-closure/PLAN-${owner}"*.md
  # shellcheck disable=SC2086
  if ! compgen -G "$ROOT/docs/plans/PLAN-038-gap-closure/PLAN-${owner}"*.md >/dev/null; then
    fail "open $gid owner $owner missing subplan file"
  fi
done < <(grep -E '^\| G-' "$REGISTRY")

pass "open non-INFO non-038g gaps have subplan files"

# Optional capability gates when present
for gate in 038d 038e 038f 038g; do
  script="$ROOT/scripts/verify-plan-${gate}.sh"
  if [[ -x "$script" ]]; then
    if bash "$script"; then
      pass "nested verify-plan-${gate}.sh"
    else
      fail "nested verify-plan-${gate}.sh"
    fi
  fi
done

# 037 docs when G-DOC-008 closed
status008="$(awk -F'|' -v id="G-DOC-008" '$2 ~ id { gsub(/ /,"",$5); print $5; exit }' "$REGISTRY")"
if [[ "$status008" == "closed" ]]; then
  [[ -f "$ROOT/docs/plans/PLAN-037-table-observability/PLAN-037-table-observability.md" ]] \
    && pass "PLAN-037 charter exists" \
    || fail "PLAN-037 charter missing"
  [[ -f "$ROOT/docs/walkthroughs/WT-037-table-observability.md" ]] \
    && pass "WT-037 exists" \
    || fail "WT-037 missing"
fi

if [[ -x "$PY" ]]; then
  "$PY" - <<'PY' || fail "registry table parse"
from pathlib import Path
text = Path("docs/plans/PLAN-038-gap-closure/registry.md").read_text(encoding="utf-8")
rows = [
    ln for ln in text.splitlines()
    if ln.startswith("| G-") and not ln.startswith("| G-ID")
]
assert rows, "no gap rows"
owners = {}
for ln in rows:
    parts = [p.strip() for p in ln.split("|")]
    # '', gid, sev, owner, status, ...
    gid, owner, status = parts[1], parts[3], parts[4]
    assert status in {"open", "closed", "wontfix"}, (gid, status)
    if status == "open":
        owners.setdefault(owner, []).append(gid)
print(f"registry_ok rows={len(rows)} open_owners={sorted(owners)}")
PY
  if [[ $? -eq 0 ]]; then pass "registry parse"; fi
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
