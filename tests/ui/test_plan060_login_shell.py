"""Browser-chrome coverage for the custom GUI login shell."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-pdf2zh-040a-auth-shell.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_auth_shell", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_short_login_shell_declares_password_manager_autocomplete_hints() -> None:
    module = _load_script_module()
    assert 'name="username" autocomplete="username"' in module.SHORT_LOGIN_HTML
    assert 'name="password" type="password" autocomplete="current-password"' in module.SHORT_LOGIN_HTML


def test_short_login_html_refresh_updates_already_patched_routes() -> None:
    module = _load_script_module()
    stale = "        _QY_SHORT_LOGIN_HTML = '<input id=\"u\" name=\"username\" required/>'\n"
    updated, changed = module._refresh_short_login_html(stale)
    assert changed is True
    assert 'autocomplete="username"' in updated
    again, changed_again = module._refresh_short_login_html(updated)
    assert changed_again is False
    assert again == updated
