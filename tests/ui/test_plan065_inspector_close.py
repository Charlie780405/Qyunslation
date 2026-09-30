# SPDX-License-Identifier: MPL-2.0
"""PLAN-065：专业词汇检查器可关闭，入库文案说明下一篇复用。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH060 = ROOT / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"
PATCH050 = ROOT / "scripts" / "apply-pdf2zh-050-workbench.py"


def test_close_hides_gradio_inspector_and_js_drawer():
    text = PATCH060.read_text(encoding="utf-8")
    assert "_qy060_close_inspector" in text
    assert "_QY060_CLOSE_OUT" in text
    assert "qy_insp_on, qy_inspector" in text
    assert "gr.update(visible=False)" in text
    assert 'qy060_close_top = gr.Button("关闭"' in text
    assert 'elem_id="qy060-insp-close"' in text
    assert "#qy050-inspector[data-open=\"false\"]" in text
    assert ".qy-050-inspector:not(#qy050-inspector)" in text
    assert "关闭 / 返回列表" not in text
    assert "_qy060_close_detail" not in text


def test_reuse_copy_says_approve_then_next_file():
    text = PATCH060.read_text(encoding="utf-8")
    assert "列表是候选" in text
    assert "下一篇登录翻译将自动使用确认译法" in text
    assert "已批准入库。" in text
    assert "下一篇登录翻译将自动使用该确认译法。" in text


def test_js_drawer_hidden_and_escape_clicks_close():
    text = PATCH050.read_text(encoding="utf-8")
    assert '#qy050-inspector[data-open="false"]' in text
    assert "display: none !important" in text
    assert "qy060-insp-close" in text
    assert "close.click()" in text
