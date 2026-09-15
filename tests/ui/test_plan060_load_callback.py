"""Regression coverage for Gradio event callback JavaScript."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-pdf2zh-060-browser-chrome.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_browser_chrome", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canvas_load_callback_is_a_function_not_an_immediately_invoked_expression() -> None:
    module = _load_script_module()
    source = """        # JavaScript: 动态调整 PDF canvas 缩放，确保完全适配容器高度
        demo.load(
            None,
            None,
            None,
            js=\"\"\"
            (function() {
              window.example = true;
            })();
            \"\"\"
        )
"""

    patched, changed = module.apply(source)

    assert changed is True
    assert "() => {" in patched
    assert "})();" not in patched
    assert module.MARKER in patched
    again, changed_again = module.apply(patched)
    assert changed_again is False
    assert again == patched
