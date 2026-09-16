# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：术语检查器改为列表裁决。"""
from pathlib import Path

PATCH = Path(__file__).resolve().parents[2] / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"


def test_plan064_list_first_actions_and_filters():
    text = PATCH.read_text(encoding="utf-8")
    assert "关闭 / 返回列表" in text
    assert "批准入库" in text
    assert "拒绝入库" in text
    assert "一键入库" in text
    assert "一键拒绝" in text
    assert "qy060_picked" in text
    assert "qy060_detail" in text
    assert "keep_selection=next_id" not in text
    assert "已批准，已返回列表" in text
    assert "已拒绝，后续不再推荐同形近义" in text
    assert 'choices=["待确认", "待管理员", "已批准", "术语未遵循", "已拒绝"]' in text
    assert "批量确认精确项" not in text
    assert "_QY060_LIST_OUT" in text
