# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：保存链路不再被空单元格顶掉，Timer 不擦确认译法。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PATCH = Path(__file__).resolve().parents[2] / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"


def _module():
    spec = importlib.util.spec_from_file_location("patch061", PATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_table_cell_does_not_override_textbox():
    text = PATCH.read_text(encoding="utf-8")
    assert "return None if not value or value in _QY060_PLACEHOLDERS else value" in text
    assert 'chosen_target = (table_target or "").strip() or (target or "").strip()' in text
    assert "该术语属高风险类别，需管理员复核后才能入库。" in text
    assert "已批准入库。下一篇登录翻译将自动使用该确认译法。" in text


def test_timer_outputs_exclude_confirmation_box():
    text = PATCH.read_text(encoding="utf-8")
    assert (
        "[qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_term_timer]"
        in text
    )
    assert "qy060_term_timer.tick" in text
    assert "keep_selection=candidate_id" in text
    assert "QYUNSLATION_TERM_BRIDGE_SECRET" not in text


def test_event_and_timer_blocks_agree_on_tick_outputs():
    module = _module()
    outputs = (
        "[qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, "
        "qy060_actual, qy060_recommended, qy060_term_timer]"
    )
    assert outputs in module.EVENT_BLOCK
    assert outputs in module.TIMER_BLOCK


def test_patch_apply_is_idempotent_and_verifies():
    module = _module()
    source = module._fixture_gui_source()
    patched, changed = module.apply(source)
    assert changed is True
    again, changed_again = module.apply(patched)
    assert changed_again is False
    assert again == patched
    if module.GUI.is_file():
        installed = module.GUI.read_text(encoding="utf-8")
        assert module.verify(module.apply(installed)[0]) == 0
