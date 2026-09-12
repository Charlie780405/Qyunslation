#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-047 delivery-loop fidelity gate.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-}"
if [[ -z "$PY" || ! -x "$PY" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
STAGE_DIR="$(mktemp -d)"
FAILURES=0
BLOCKED=0
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
blocked() { printf 'BLOCKED: %s\n' "$1"; BLOCKED=$((BLOCKED + 1)); }

run_pass() {
  local label="$1" log="$2"
  shift 2
  if "$@" >"$log" 2>&1; then pass "$label"
  else fail "$label"; tail -n 40 "$log"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=0 fail=1\n'
  exit 1
fi

PLAN_DIR="$ROOT/docs/plans/PLAN-047-delivery-loop-fidelity"
[[ -f "$PLAN_DIR/PLAN-047-delivery-loop-fidelity.md" ]] \
  && pass "PLAN-047 charter" || fail "missing PLAN-047 charter"
for f in PLAN-047a-deploy-fingerprint.md PLAN-047b-qc-channel.md \
  PLAN-047c-no-drop.md PLAN-047d-paragraph-layout.md \
  PLAN-047e-table-normalize.md PLAN-047f-image-rotate-group.md \
  PLAN-047g-skill-capture.md; do
  [[ -f "$PLAN_DIR/$f" ]] && pass "$f" || fail "missing $f"
done

# 047a
[[ -x "$ROOT/scripts/deploy-translate-stack.sh" ]] \
  && pass "047a deploy script" || fail "047a deploy script"
grep -q 'image-translate-health' "$ROOT/qyunslation/custom_api.py" \
  && pass "047a health endpoint" || fail "047a health endpoint"
grep -q 'assert_sidecar_in_sync\|code_fingerprint' "$ROOT/scripts/pdf_image_translate.py" \
  && pass "047a sync gate" || fail "047a sync gate"
grep -q 'def code_fingerprint\|def capability_probe' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "047a fingerprint helpers" || fail "047a fingerprint helpers"

# 047b
grep -q 'X-Image-QC' "$ROOT/qyunslation/custom_api.py" \
  && pass "047b X-Image-QC header" || fail "047b X-Image-QC"
grep -q 'qc_channel\|QC_CHANNEL_BLIND\|_parse_sidecar_qc' \
  "$ROOT/scripts/pdf_image_translate.py" \
  && pass "047b qc_channel" || fail "047b qc_channel"

# 047c
grep -q '不折进 fit\|不折 fit' "$ROOT/scripts/doc_profile.py" \
  && pass "047c no fold fit" || fail "047c still folds fit"
grep -q 'max(0.5 \* font_size' "$ROOT/scripts/doc_profile.py" \
  && pass "047c overflow tol" || fail "047c overflow tol"
grep -q 'min_scale = 0.12' "$ROOT/scripts/doc_profiles.toml" \
  && pass "047c min_scale 0.12" || fail "047c min_scale"
grep -q 'def reset_min_scale' "$ROOT/scripts/doc_profile.py" \
  && pass "047c reset_min_scale" || fail "047c reset_min_scale"
[[ -f "$ROOT/scripts/apply-pdf2zh-047c-no-drop.py" ]] \
  && pass "047c patcher" || fail "047c patcher"
grep -q 'apply-pdf2zh-047c-no-drop.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "047c in service" || fail "047c not in service"
PC="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/backend/pdf_creater.py"
if [[ -f "$PC" ]] && grep -q '_QY_047C_NO_DROP' "$PC"; then
  pass "047c no-drop present"
else
  if "$PY" "$ROOT/scripts/apply-pdf2zh-047c-no-drop.py" >"$STAGE_DIR/047c.log" 2>&1 \
    && grep -q '_QY_047C_NO_DROP' "$PC"; then
    pass "047c no-drop applied"
  else
    fail "047c no-drop missing"
  fi
fi

# 047d
[[ -f "$ROOT/scripts/apply-pdf2zh-047d-para-layout.py" ]] \
  && pass "047d patcher" || fail "047d patcher"
grep -q 'apply-pdf2zh-047d-para-layout.py' "$ROOT/scripts/pdf2zh.service" \
  && pass "047d in service" || fail "047d not in service"
PF="$HOME/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/babeldoc/format/pdf/document_il/midend/paragraph_finder.py"
if [[ -f "$PF" ]] && grep -q '_QY_047D_PARA_LAYOUT' "$PF"; then
  pass "047d para layout present"
else
  if "$PY" "$ROOT/scripts/apply-pdf2zh-047d-para-layout.py" >"$STAGE_DIR/047d.log" 2>&1 \
    && grep -q '_QY_047D_PARA_LAYOUT' "$PF"; then
    pass "047d para layout applied"
  else
    fail "047d para layout missing"
  fi
fi
grep -q '_DOSE_CALQUES\|_DRUG_CALQUES' "$ROOT/qyunslation/structure/text_sanitize.py" \
  && pass "047d dose/drug calques" || fail "047d calques"

# 047e
grep -q 'n_cols > mid \* 2.0' "$ROOT/qyunslation/structure/table_qc.py" \
  && pass "047e cluster drift" || fail "047e cluster drift"
grep -q 'TABLE_QC_SOFT_LITERATURE' "$ROOT/qyunslation/structure/table_qc.py" \
  && pass "047e soft literature" || fail "047e soft literature"
[[ -f "$ROOT/scripts/pdf_table_normalize.py" ]] \
  && pass "047e normalize script" || fail "047e normalize"
grep -q 'normalize_failed_tables\|pdf_table_normalize' \
  "$ROOT/scripts/pdf_table_translate.py" \
  && pass "047e normalize wired" || fail "047e normalize wired"

# 047f
grep -q 'def _group_vertical_runs' "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "047f vertical runs" || fail "047f vertical runs"
grep -q 'ERASE_COVER_MIN\|TIER_K_FLOOR.*, \"0.95\"' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "047f cover/k floor" || fail "047f cover/k"
grep -q 'FIGURE_TIER_MIN_PX.*, \"22\"' \
  "$ROOT/qyunslation/extensions/image_translate.py" \
  && pass "047f min px 22" || fail "047f min px"

# 047g skills
for slug in translate-stack-process-boundary babeldoc-patch-safety \
  literature-paragraph-layout translation-content-integrity \
  translation-pitfall-capture; do
  [[ -f "$ROOT/.cursor/skills/$slug/SKILL.md" ]] \
    && pass "skill $slug" || fail "skill $slug"
done
[[ -f "$ROOT/.cursor/skills/skill-registry/error-signatures.toml" ]] \
  && pass "error-signatures" || fail "error-signatures"
[[ -x "$ROOT/scripts/skill-pitfall-capture.py" ]] \
  && pass "capture script" || fail "capture script"
[[ -f "$ROOT/.cursor/hooks.json" ]] \
  && pass "hooks.json" || fail "hooks.json"
grep -q 'SK-Q004' "$ROOT/.cursor/skills/skill-registry/registry.md" \
  && pass "registry Q004+" || fail "registry Q004+"

# unit smokes
run_pass "047 unit sanitize/cluster/rotate" "$STAGE_DIR/unit.log" \
  "$PY" - <<'PY'
from qyunslation.structure.text_sanitize import apply_forced_terms
assert "曲罗芦单抗" in apply_forced_terms("特罗金单抗")
assert "每2周一次" in apply_forced_terms("每周两次（Q2W）")
assert "gs" not in apply_forced_terms("我们的发现gs可以帮助")
from qyunslation.structure.table_qc import detect_column_cluster_drift
class B:
    def __init__(self, t, r=0, c=0):
        self.source_text=t; self.row_index=r; self.column_index=c
blocks=[B("="), B(")"), B("N"), B("hello",0,0), B("world",0,1)]
assert detect_column_cluster_drift(blocks) is None
from qyunslation.extensions.image_translate import (
    _group_vertical_runs, _is_ocr_garbage, code_fingerprint, capability_probe,
)
assert _is_ocr_garbage("F08", 0.95)
boxes=[[10,10,20,20,"C",0.9],[10,22,20,32,"u",0.9],[10,34,20,44,"m",0.9],[10,46,20,56,"p",0.9]]
nb, nt, _ = _group_vertical_runs(boxes, [b[4] for b in boxes])
assert len(nb) == 1 and len(nt[0]) >= 3
assert len(code_fingerprint()) == 12
assert capability_probe()["figure_tier_min_px"] == 22
print("ok")
PY

# capture dry-run
run_pass "047 capture dry-run" "$STAGE_DIR/capture.log" \
  "$PY" "$ROOT/scripts/skill-pitfall-capture.py"

# capture inbox from synthetic unknown error
printf 'ERROR: totally_unknown_widget_xyz exploded\n' >"$STAGE_DIR/fake.log"
run_pass "047 capture inbox" "$STAGE_DIR/capture2.log" \
  "$PY" "$ROOT/scripts/skill-pitfall-capture.py" --log "$STAGE_DIR/fake.log"
grep -q 'totally_unknown_widget_xyz\|unknown_widget' \
  "$ROOT/.cursor/skills/skill-registry/pitfalls-inbox.md" \
  && pass "047 inbox entry" || fail "047 inbox entry"

# sample job assertions (optional env)
SAMPLE_DIR="${QYUNSLATION_PLAN047_SAMPLE:-}"
if [[ -n "$SAMPLE_DIR" && -d "$SAMPLE_DIR" ]]; then
  MONO="$(ls -t "$SAMPLE_DIR"/*.mono.pdf 2>/dev/null | head -1 || true)"
  if [[ -n "$MONO" && -f "$MONO" ]]; then
    run_pass "047 sample keywords" "$STAGE_DIR/sample.log" \
      "$PY" - <<PY
import pymupdf
d=pymupdf.open("$MONO")
blob="\\n".join(p.get_text() for p in d)
for k in ("摘要", "目的"):
    assert k in blob, k
print("keywords ok")
PY
  else
    blocked "047 sample mono.pdf missing"
  fi
else
  blocked "QYUNSLATION_PLAN047_SAMPLE unset (runtime sample checks)"
fi

# sidecar health if up
if curl -sf "http://127.0.0.1:8010/service/image-translate-health" >"$STAGE_DIR/health.json" 2>/dev/null; then
  run_pass "047 sidecar fingerprint match" "$STAGE_DIR/fp.log" \
    "$PY" - <<PY
import hashlib, json
from pathlib import Path
j=json.load(open("$STAGE_DIR/health.json"))
local=hashlib.sha256(Path("qyunslation/extensions/image_translate.py").read_bytes()).hexdigest()[:12]
remote=j.get("code_fingerprint") or ""
assert local==remote, (local, remote)
print("match", local)
PY
else
  blocked "sidecar health unreachable (deploy not run yet)"
fi

printf 'SUMMARY: %s blocked=%s fail=%s\n' \
  "$([[ $FAILURES -eq 0 ]] && echo PASS || echo FAIL)" "$BLOCKED" "$FAILURES"
exit "$([[ $FAILURES -eq 0 ]] && echo 0 || echo 1)"
