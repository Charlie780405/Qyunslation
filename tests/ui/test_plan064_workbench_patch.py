# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：术语检查器改为列表裁决。"""
from pathlib import Path

PATCH = Path(__file__).resolve().parents[2] / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"


def test_plan064_list_first_actions_and_filters():
    text = PATCH.read_text(encoding="utf-8")
    assert 'gr.Button("关闭"' in text
    assert "_qy060_close_inspector" in text
    assert "批准入库" in text
    assert "拒绝入库" in text
    assert "一键入库" in text
    assert "一键拒绝" in text
    assert "qy060_picked" in text
    assert "qy060_detail" in text
    assert "keep_selection=next_id" not in text
    assert "已批准入库。" in text
    assert "下一篇登录翻译将自动使用该确认译法。" in text
    assert "已拒绝，后续不再推荐同形近义" in text
    assert "qy060_decision_status" in text
    assert 'elem_id="qy060-decision-status"' in text
    assert 'elem_id="qy060-term-table"' in text
    assert 'elem_id="qy060-picked"' in text
    assert 'elem_id="qy060-batch-row"' in text
    assert 'max_height="28vh"' in text
    assert "height: max-content" in text
    assert "z-index: 200" in text
    assert ".qy-050-inspector.hidden" in text
    assert "display: none !important" in text
    assert "_qy060_batch_feedback" in text
    assert "高风险（药名/靶点/方案号等）" in text
    assert "已从「待确认」移到「已批准」" in text
    assert "_QY060_DECIDE_OUT = [qy060_decision_status, qy060_term_filter]" in text
    assert 'choices=["待确认", "待管理员", "已批准", "术语未遵循", "已拒绝"]' in text
    assert "批量确认精确项" not in text
    assert "_QY060_LIST_OUT" in text
