# SPDX-License-Identifier: MPL-2.0
"""PLAN-060：术语面板补丁保持幂等，且不把桥接密钥送入浏览器。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "scripts" / "apply-pdf2zh-060-termbase-workbench.py"


def _module():
    spec = importlib.util.spec_from_file_location("patch060", PATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan060_patch_declares_server_side_term_panel_and_callbacks():
    text = PATCH.read_text(encoding="utf-8")
    assert "qy060_term_badge" in text
    assert "qy060_term_table" in text
    assert "gr.Request" in text
    assert "prepare_workbench_translation" in text
    assert "complete_workbench_translation" in text
    assert "QYUNSLATION_TERM_BRIDGE_SECRET" not in text
    assert "overflow-y: auto" in text
    assert "保存术语决定" in text
    assert "_qy_060_term_bridge_early_complete" in text
    assert "_qy_060_term_review_timer" in text
    assert "link_input,\n    request: gr.Request | None = None,\n    *ui_args" in text
    assert 'headers=["源词", "实际译法", "推荐译法", "确认译法"' in text
    assert "interactive=True" in text
    assert "static_columns=[0, 1, 2, 4, 5, 6, 7]" in text
    assert "未可靠对齐" in text
    assert "暂无 AI 推荐" in text
    assert "实际译法（原文证据）" in text
    assert "推荐译法（AI 建议）" in text
    assert "确认译法（保存采用）" in text
    assert "_qy060_table_confirmation" in text
    assert "_qy060_select_table_row" in text
    assert "_qy060_table_input" in text
    assert "已返回候选列表并定位下一条" in text
    assert "qy060_term_table.input" in text


def test_plan060_migrates_request_before_varargs_for_gradio_injection():
    module = _module()
    source = module.PY_MARKER + "\n" + module._TRANSLATE_SIGNATURE_LEGACY

    patched, changed = module.apply_python_hook(source)

    assert changed is True
    assert module._TRANSLATE_SIGNATURE_PATCHED in patched
    assert patched.index("request: gr.Request") < patched.index("*ui_args")


def test_plan060_extracts_terms_before_slow_image_postprocessing():
    module = _module()
    source = """            # _qy_imgtr_post
            do_slow_image_postprocessing()

            result_entry = {
"""

    patched, changed = module.apply_complete_hook(source)

    assert changed is True
    assert module.EARLY_COMPLETE_MARKER in patched
    assert patched.index(module.EARLY_COMPLETE_MARKER) < patched.index("# _qy_imgtr_post")
    assert module.COMPLETE_MARKER in patched
    assert patched.index("# _qy_imgtr_post") < patched.index(module.COMPLETE_MARKER)


def test_plan060_migrates_old_patch_done_flag_to_final_completion_only():
    module = _module()
    source = f'''            {module.EARLY_COMPLETE_MARKER}
            try:
                pass
            except Exception:
                pass
            finally:
                state["_qy060_term_done"] = True

            # _qy_imgtr_post
            do_slow_image_postprocessing()

            {module.COMPLETE_MARKER}
            try:
                pass
            except Exception:
                state["_qy060_term_note"] = "术语候选提取降级；译文已生成，未自动写入共享词库。"

            result_entry = {{
'''

    patched, changed = module.apply_complete_hook(source)

    assert changed is True
    early_start = patched.index(module.EARLY_COMPLETE_MARKER)
    early_end = patched.index("# _qy_imgtr_post")
    final_start = patched.index(module.COMPLETE_MARKER)
    assert 'state["_qy060_term_done"] = True' not in patched[early_start:early_end]
    assert 'state["_qy060_term_done"] = True' in patched[final_start:]


def test_plan060_migrates_existing_term_ui_and_events_without_duplicate_blocks():
    module = _module()
    ui_source = (
        f"        {module.UI_MARKER}\n"
        "        gr.Markdown(\"old term fields\")\n"
        "        qy_help_on = gr.State(False)\n"
    )
    ui_patched, ui_changed = module.apply_ui(ui_source)
    assert ui_changed is True
    assert "实际译法（原文证据）" in ui_patched
    ui_again, ui_changed_again = module.apply_ui(ui_patched)
    assert ui_changed_again is False
    assert ui_again == ui_patched

    event_source = (
        f"        {module.EVENT_MARKER}\n"
        "        old_term_events()\n"
        "        # _qy_office_preview_then\n"
    )
    event_patched, event_changed = module.apply_events(event_source)
    assert event_changed is True
    assert "qy060_term_table.input" in event_patched
    event_again, event_changed_again = module.apply_events(event_patched)
    assert event_changed_again is False
    assert event_again == event_patched


def test_plan060_css_replaces_existing_block_and_stays_idempotent():
    module = _module()
    source = "    /* _qy_060_term_review_css */\n    .old {}\n    /* _qy_050_workbench_css */\n"
    patched, changed = module.apply_css(source)
    assert changed is True
    assert "overflow-y: auto" in patched
    assert ".old {}" not in patched
    again, changed_again = module.apply_css(patched)
    assert changed_again is False
    assert again == patched


def test_plan060_patch_is_idempotent_on_supported_gui_anchors():
    module = _module()
    source = module._fixture_gui_source()
    patched, changed = module.apply(source)
    assert changed is True
    assert patched.count(module.PY_MARKER) == 1
    assert patched.count(module.UI_MARKER) == 1
    assert patched.count(module.EVENT_MARKER) == 1
    repeated, changed_again = module.apply(patched)
    assert changed_again is False
    assert repeated == patched


def test_plan060_patch_compiles_against_installed_upstream_gui_when_available():
    module = _module()
    if not module.GUI.is_file():
        pytest.skip("pdf2zh-next GUI is not installed in this test environment")
    patched, _changed = module.apply(module.GUI.read_text(encoding="utf-8"))
    assert module.verify(patched) == 0
    compile(patched, str(module.GUI), "exec")
