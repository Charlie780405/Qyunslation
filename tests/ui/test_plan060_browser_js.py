"""Regression coverage for JavaScript injected into the production Gradio shell."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-pdf2zh-sse-recover.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_sse_recover", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sse_recover_js_is_a_parseable_gradio_function() -> None:
    """A malformed injected regex must not blank the authenticated workbench."""
    module = _load_script_module()
    rendered = ast.parse(f'payload = """{module.JS_BLOCK}"""').body[0].value.value
    result = subprocess.run(
        ["node", "-e", "new Function('return (' + require('fs').readFileSync(0, 'utf8') + ')')"],
        input=f"() => {{{rendered}\n}}",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
