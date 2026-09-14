# SPDX-License-Identifier: MPL-2.0
"""Regression coverage for the compact app bar and upload action guard."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "scripts/apply-pdf2zh-050-workbench.py"


def _source() -> str:
    return PATCH.read_text(encoding="utf-8")


def _patch_module():
    spec = importlib.util.spec_from_file_location("patch050", PATCH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_desktop_appbar_is_single_line_and_children_are_not_stretched():
    text = _source()
    css = text.split("JS_BLOCK", 1)[0]

    assert "display: grid !important" in css
    assert "height: var(--qy-appbar-h) !important" in css
    assert "max-height: var(--qy-appbar-h) !important" in css
    assert ".qy-050-appbar .wrap" in css
    assert "height: auto !important" in css
    assert ".qy-050-control" in css
    assert "overflow: hidden !important" in css
    assert "color: #fff !important" in css


def test_mobile_appbar_retains_responsive_wrap():
    text = _source()
    css = text.split("JS_BLOCK", 1)[0]

    mobile = css.split("@media (max-width: 767px)", 1)[1]
    assert ".qy-050-appbar {" in mobile
    assert "grid-template-columns:" in mobile
    assert "height: auto !important;" in mobile


def test_upload_keeps_translation_action_visible_and_reachable():
    text = _source()
    css = text.split("JS_BLOCK", 1)[0]

    assert ".qy-col-left > .action-row" in css
    assert "order: -1 !important" in css
    assert "visibility: visible !important" in css
    assert "_qy_060_upload_action_guard" in text
    assert "_qy060_show_translate_action" in text
    assert "outputs=[translate_btn]" in text
    assert "file_input.upload(" in text
    assert "file_input.change(" in text


def test_appbar_uses_compact_non_wrapping_controls_and_preserves_values():
    text = _source()
    assert "qy_dir = gr.Dropdown" in text
    assert "qy_mode = gr.Dropdown" in text
    assert 'choices=["英→中", "中→英"]' in text
    assert 'choices=["快速", "专业"]' in text
    assert 'elem_classes=["qy-050-control", "qy-050-dir"]' in text
    assert 'elem_classes=["qy-050-control", "qy-050-mode"]' in text


def test_upload_action_guard_is_idempotent_and_has_a_stable_anchor():
    module = _patch_module()
    original = "        # Handle file clear/delete event\n"

    updated, changed = module.apply_action_guard(original)
    assert changed is True
    assert updated.count(module.ACTION_GUARD_MARKER) == 1

    updated_again, changed_again = module.apply_action_guard(updated)
    assert changed_again is False
    assert updated_again == updated
