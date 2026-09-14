# SPDX-License-Identifier: MPL-2.0
"""PLAN-050a：真实运行时施工面（Gradio 补丁链，不是 Vue frontend/）。"""
from __future__ import annotations

from pathlib import Path

PRODUCTION_SURFACE = "gradio-pdf2zh-7860"
SERVICE_UNIT = "pdf2zh.service"
GUI_PORT = 7860
SIDECAR_PORT = 8010
VUE_FRONTEND = Path("/home/dev/qyunslation/frontend")
SERVICE_FILE = Path("/home/dev/qyunslation/scripts/pdf2zh.service")


def describe_surface() -> dict[str, object]:
    """静态描述生产施工面；不探测网络。"""
    vue_dist = VUE_FRONTEND / "dist"
    return {
        "surface": PRODUCTION_SURFACE,
        "entry": "pdf2zh_next --gui --server-port 7860",
        "service": SERVICE_UNIT,
        "service_file": str(SERVICE_FILE),
        "vue_loaded": False,
        "vue_dist_exists": vue_dist.is_dir(),
        "note": "Caddy translate.qyunsgen.com 兜底反代 :7860；/api/v1 → sidecar :8010",
    }
