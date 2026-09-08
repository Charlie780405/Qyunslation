#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0
# PLAN-030h cross-format fidelity gate. Do not nest 028-030g.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${QYUNSLATION_VERIFY_PY:-$ROOT/.venv/bin/python}"
SYSTEM_PY="${QYUNSLATION_PATCH_PY:-/usr/bin/python3}"
TEST_TIMEOUT_SECONDS="${QYUNSLATION_VERIFY_TIMEOUT_SECONDS:-900}"
SIDECAR_URL="${QYUNSLATION_SIDECAR_URL:-http://127.0.0.1:8010}"
STAGE_DIR="$(mktemp -d)"
FAILURES=0

cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT

cd "$ROOT" || exit 1

fail() { printf 'FAIL: %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf 'PASS: %s\n' "$1"; }
info() { printf 'INFO: %s\n' "$1"; }

show_failure_log() { [[ -f "$1" ]] && tail -n 60 "$1"; }

run_pass() {
  local label="$1" log_path="$2"
  shift 2
  if "$@" >"$log_path" 2>&1; then pass "$label"
  else fail "$label"; show_failure_log "$log_path"; fi
}

if [[ ! -x "$PY" ]]; then
  printf 'SUMMARY: FAIL blocked=1 fail=0\n'
  exit 1
fi

run_pass "PLAN-030h modules compile" "$STAGE_DIR/compile.log" \
  "$PY" -m compileall -q \
    qyunslation/structure/capabilities.py \
    qyunslation/custom_api.py \
    scripts/_gui_extensions.py \
    scripts/apply-pdf2zh-office-route.py \
    scripts/apply-pdf2zh-office-preview.py \
    scripts/apply-pdf2zh-preview-url.py \
    scripts/apply-pdf2zh-prescan.py \
    scripts/apply-pdf2zh-dual-preview.py

# 补丁链跑在系统 python 下（见 pdf2zh.service 的 ExecStartPre），清单必须在那里也能载入
run_pass "extension manifest loads under the patch runtime" "$STAGE_DIR/manifest.log" \
  env PYTHONPATH="$ROOT" "$SYSTEM_PY" "$ROOT/scripts/_gui_extensions.py"

run_pass "H2 GUI extension manifest contract" "$STAGE_DIR/gui-manifest.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_gui_extension_manifest.py

run_pass "H3 cross-format semantic parity" "$STAGE_DIR/parity.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_cross_format_parity.py

run_pass "H4 layout gold samples" "$STAGE_DIR/layout.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_layout_gold_samples.py

run_pass "H1 synthetic fixtures reproduce and match the catalog" "$STAGE_DIR/catalog.log" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q --no-cov tests/structure/test_fixture_catalog.py

# H1 的核心主张：断言不依赖运行时样本目录。指向空目录重跑，失败数必须为零。
NOSAMPLE_XML="$STAGE_DIR/nosample.xml"
NOSAMPLE_LOG="$STAGE_DIR/nosample.log"
if env QYUNSLATION_SAMPLE_ROOT="$STAGE_DIR/absent-samples" \
  timeout --signal=INT --kill-after=10s "${TEST_TIMEOUT_SECONDS}s" \
  "$PY" -m pytest -q tests/structure --no-cov \
    --junitxml="$NOSAMPLE_XML" >"$NOSAMPLE_LOG" 2>&1; then
  if "$PY" - "$NOSAMPLE_XML" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.parse(Path(sys.argv[1])).getroot()
xfails = {
    case.attrib["name"]
    for case in root.findall(".//testcase")
    if (node := case.find("skipped")) is not None
    and node.attrib.get("type") == "pytest.xfail"
}
assert xfails == set(), xfails
assert not root.findall(".//failure")
assert not root.findall(".//error")

passed = sum(
    1
    for case in root.findall(".//testcase")
    if case.find("skipped") is None and case.find("failure") is None
)
# 合成夹具必须撑起绝大部分断言；外部样本缺席时不能塌成一小撮
assert passed >= 280, passed
PY
  then
    pass "structure suite is green without any runtime sample directory"
  else
    fail "structure suite regressed without runtime samples"
    show_failure_log "$NOSAMPLE_LOG"
  fi
else
  fail "structure suite failed without runtime samples"
  show_failure_log "$NOSAMPLE_LOG"
fi

# H2 端到端：五种 CORE 图片格式都要被 sidecar 受理，不能返回 unsupported_format
if curl -fsS -o /dev/null --max-time 5 "$SIDECAR_URL/" 2>/dev/null; then
  SIDECAR_LOG="$STAGE_DIR/sidecar.log"
  if env QYUNSLATION_SIDECAR_URL="$SIDECAR_URL" "$PY" - <<'PY' >"$SIDECAR_LOG" 2>&1
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "plan030h_fixtures", "tests/fixtures/structure/generate_synthetic.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
staged = Path(tempfile.mkdtemp())
generator.generate_all(staged)

url = os.environ["QYUNSLATION_SIDECAR_URL"].rstrip("/")
rejected = []
for name in ("poster.png", "photo.jpg", "diagram.webp", "scan.bmp", "multipage.tiff"):
    result = subprocess.run(
        [
            "curl", "-sS", "-X", "POST", f"{url}/service/image-probe",
            "-F", f"file=@{staged / name}",
            "-F", "to_lang=简体中文",
            "--max-time", "60",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    reason = str(payload.get("reason", ""))
    print(f"{name}: status={payload.get('status')} reason={reason}")
    if reason.startswith("unsupported_format"):
        rejected.append(name)

assert not rejected, rejected
PY
  then
    pass "sidecar accepts every CORE image format"
  else
    fail "sidecar rejected a declared CORE image format"
    show_failure_log "$SIDECAR_LOG"
  fi
else
  info "sidecar probe skipped, $SIDECAR_URL is unreachable"
fi

# H2 生产侧：已安装的 GUI 与清单一致（未装 pdf2zh 时上面的契约测试会自行 skip）
GUI_PATH="/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
if [[ -f "$GUI_PATH" ]]; then
  if "$PY" - "$GUI_PATH" <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, ".")
from qyunslation.structure.capabilities import (  # noqa: E402
    gui_image_extensions,
    gui_sidecar_extensions,
)

source = Path(sys.argv[1]).read_text(encoding="utf-8")
expected = "{" + ", ".join(f'"{e}"' for e in sorted(gui_sidecar_extensions())) + "}"
assert f"_QY_OFFICE_SIDECAR_EXT = {expected}" in source, "sidecar ext drifted"
for ext in gui_image_extensions():
    assert f'"{ext}"' in source, ext
PY
  then
    pass "installed GUI carries the rendered manifest"
  else
    fail "installed GUI drifted from the capability manifest"
  fi
else
  info "installed GUI check skipped, pdf2zh is not on this host"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  printf 'SUMMARY: PASS fail=0\n'
  exit 0
fi
printf 'SUMMARY: FAIL fail=%d\n' "$FAILURES"
exit 1
