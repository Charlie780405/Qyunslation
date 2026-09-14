# SPDX-License-Identifier: MPL-2.0
"""PLAN-057：壳层去重与高级区滚动。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/dev/qyunslation")
PATCH = ROOT / "scripts/apply-pdf2zh-050-workbench.py"


def test_plan057_chrome_dedupe():
    text = PATCH.read_text(encoding="utf-8")
    css = text.split("JS_BLOCK", 1)[0]
    body = text.split("def verify", 1)[0]
    assert "qy_dir = gr.Radio" in text
    assert "qy_help = gr.Column(" in text
    assert "qy_inspector = gr.Column(" in text
    assert "qy_help = gr.Accordion(" not in body
    assert "qy_inspector = gr.Accordion(" not in body
    assert 'elem_classes=["lang-row"], visible=False' in text
    assert "min(55vh, 560px)" in css
    assert ".qy-col-left > .qy-adv-acc > :last-child" in css
    assert "apply_adv_scroll" in text
    assert ".qy-col-left .lang-row" in css
    assert "# _qy_057_appbar_begin" in text
    assert "禁止再写入 Gradio js=" in text


def test_plan057_docs_enlisted():
    plans = ROOT / "docs/plans"
    assert (plans / "PLAN-057-chrome-dedupe/PLAN-057-chrome-dedupe.md").is_file()
    idx = (plans / "README.md").read_text(encoding="utf-8")
    assert "PLAN-057-chrome-dedupe" in idx
