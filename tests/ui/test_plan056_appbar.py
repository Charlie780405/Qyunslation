# SPDX-License-Identifier: MPL-2.0
"""PLAN-056：应用栏方向开关（057 后检查器改为 Column 面板）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/dev/qyunslation")
PATCH = ROOT / "scripts/apply-pdf2zh-050-workbench.py"


def test_plan056_appbar_controls():
    text = PATCH.read_text(encoding="utf-8")
    css = text.split("JS_BLOCK", 1)[0]
    assert "qy_dir = gr.Radio" in text
    assert "英→中" in text
    assert "中→英" in text
    # 057 覆盖：面板为 Column，不再是 Accordion
    assert "qy_help = gr.Column(" in text or "qy_help = gr.Accordion(" in text
    assert "qy_inspector = gr.Column(" in text or "qy_inspector = gr.Accordion(" in text
    assert "qy_dir.change(" in text
    assert "scale=0" in text
    assert "translateX(100%)" not in css
    assert "方向在左侧" not in text.split("def verify", 1)[0]
    assert "禁止再写入 Gradio js=" in text


def test_plan056_docs_enlisted():
    plans = ROOT / "docs/plans"
    assert (plans / "PLAN-056-appbar-inspector-ux/PLAN-056-appbar-inspector-ux.md").is_file()
    idx = (plans / "README.md").read_text(encoding="utf-8")
    assert "PLAN-056-appbar-inspector-ux" in idx
