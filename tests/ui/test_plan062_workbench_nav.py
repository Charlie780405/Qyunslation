# SPDX-License-Identifier: MPL-2.0
"""PLAN-062：保存后定位下一条、Concept 下拉、筛选项。"""
from pathlib import Path

PATCH = Path(__file__).resolve().parents[2] / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"


def test_patch_advances_to_next_term_and_exposes_concept_picker():
    text = PATCH.read_text(encoding="utf-8")
    assert "keep_selection=next_id" in text
    assert "本次待确认术语已全部处理" in text
    assert 'choices=["待确认", "待管理员", "已应用", "术语未遵循", "已处理"]' in text
    assert "gr.Dropdown(choices=[], allow_custom_value=True" in text
    assert "search_workbench_concepts" in text
    assert "需人工填写" in text
    assert "_qy060_confirm_default" in text
    assert "restore_latest_workbench_run" in text
    assert "_qy060_ensure_run" in text
    assert "登录后将恢复最近一次翻译" in text
    assert 'selected_filter in {{"已处理", "已应用"}}' in text
    assert "source_norm" in text
