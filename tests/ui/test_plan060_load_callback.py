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


def test_canvas_load_callback_accepts_legacy_function_marker() -> None:
    module = _load_script_module()
    source = """        # JavaScript: 动态调整 PDF canvas 缩放，确保完全适配容器高度
        demo.load(
            None,
            None,
            None,
            js=\"\"\"
            () => {
                // _qy_060_canvas_load_fn
              window.example = true;
            }
            \"\"\"
        )
"""

    patched, changed = module.apply(source)

    assert changed is False
    assert patched == source
    again, changed_again = module.apply(patched)
    assert changed_again is False
    assert again == patched


def test_browser_font_aliases_are_created_from_existing_gradio_fonts(tmp_path) -> None:
    module = _load_script_module()
    for family, regular, bold in (
        ("IBMPlexSans", "IBMPlexSans-Regular.woff2", "IBMPlexSans-Bold.woff2"),
        ("IBMPlexMono", "IBMPlexMono-Regular.woff2", "IBMPlexMono-Bold.woff2"),
    ):
        folder = tmp_path / family
        folder.mkdir()
        (folder / regular).write_bytes(f"{family}-regular".encode())
        (folder / bold).write_bytes(f"{family}-bold".encode())

    created, warnings = module.ensure_font_aliases(tmp_path)

    assert created == 8
    assert warnings == []
    assert (tmp_path / "ui-sans-serif" / "ui-sans-serif-Regular.woff2").is_file()
    assert (tmp_path / "system-ui" / "system-ui-Bold.woff2").is_file()
    assert (tmp_path / "ui-monospace" / "ui-monospace-Regular.woff2").is_file()
    assert (tmp_path / "Consolas" / "Consolas-Bold.woff2").is_file()
    again_created, again_warnings = module.ensure_font_aliases(tmp_path)
    assert again_created == 0
    assert again_warnings == []
