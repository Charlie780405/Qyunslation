# SPDX-License-Identifier: MPL-2.0
"""PLAN-050b–f：工作台补丁脚本可静态校验。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "scripts/apply-pdf2zh-050-workbench.py"


def test_workbench_patch_exists():
    text = PATCH.read_text(encoding="utf-8")
    css = text.split("JS_BLOCK", 1)[0]
    assert "qy-050-appbar" in text
    assert "qy_help_btn" in text
    assert "qy_mode.change" in text
    assert "qy_dir = gr.Dropdown" in text
    assert "focus-visible" in text
    assert "禁止再写入 Gradio js=" in text
    assert "translateX(100%)" not in css


def test_service_registers_050_patch():
    svc = (ROOT / "scripts/pdf2zh.service").read_text(encoding="utf-8")
    assert "apply-pdf2zh-050-workbench.py" in svc
    # 须在 viewer / prescan 之后
    assert svc.index("apply-pdf2zh-prescan.py") < svc.index(
        "apply-pdf2zh-050-workbench.py"
    )
