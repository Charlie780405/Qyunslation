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
