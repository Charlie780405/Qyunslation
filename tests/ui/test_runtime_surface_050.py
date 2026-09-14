# SPDX-License-Identifier: MPL-2.0
"""PLAN-050a：施工面与补丁链静态门（不改生产 UI）。"""
from __future__ import annotations

from pathlib import Path

from qyunslation.ui.surface import PRODUCTION_SURFACE, SERVICE_FILE, describe_surface

ROOT = Path("/home/dev/qyunslation")


def test_surface_is_gradio_not_vue():
    info = describe_surface()
    assert info["surface"] == PRODUCTION_SURFACE
    assert info["vue_loaded"] is False
    assert "7860" in str(info["entry"])


def test_service_starts_gui_not_frontend():
    text = SERVICE_FILE.read_text(encoding="utf-8")
    assert "pdf2zh_next --gui" in text
    assert "--server-port 7860" in text
    assert "apply-pdf2zh-dual-preview.py" in text
    assert "apply-pdf2zh-left-dock.py" in text


def test_vue_dist_not_production_asset():
    assert not (ROOT / "frontend" / "dist").is_dir()


def test_patch_order_lists_gui_chain():
    order = (ROOT / "docs/contracts/pdf2zh-patch-order.md").read_text(encoding="utf-8")
    assert "apply-pdf2zh-dual-preview.py" in order
    assert "apply-pdf2zh-prescan.py" in order
