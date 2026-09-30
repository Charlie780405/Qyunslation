from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_next_build_uses_isolated_asset_namespace():
    vite = (FRONTEND / "vite.config.js").read_text(encoding="utf-8")
    assert "base: '/app-assets/'" in vite
    assert "outDir: '../qyunslation/static/app'" in vite


def test_next_app_exposes_clinical_routes_and_design_tokens():
    app = (FRONTEND / "src/next/AppNext.vue").read_text(encoding="utf-8")
    shell = (FRONTEND / "src/next/components/AppShell.vue").read_text(encoding="utf-8")
    router = (FRONTEND / "src/next/router.js").read_text(encoding="utf-8")
    session = (FRONTEND / "src/next/stores/session.js").read_text(encoding="utf-8")
    login = (FRONTEND / "src/next/pages/LoginPage.vue").read_text(encoding="utf-8")
    settings = (FRONTEND / "src/components/settings/SettingsPanel.vue").read_text(encoding="utf-8")
    styles = (FRONTEND / "src/next/next.css").read_text(encoding="utf-8")

    for route in ("/login", "/workbench", "/termbase", "/settings"):
        assert route in router
    assert "Qyunslation" in shell
    assert "--qy-primary: #005076" in styles
    assert "--qy-brand-green: #81BB39" in styles
    assert "workbench_v2" in router
    assert "hasCapability" in session
    assert "workbench_v2" in login
    assert '/app-assets/qyunslation-mark.png' in shell
    assert '/app-assets/qyunslation-mark.png' in login
    assert '/static/qyunslation-logo.png' in settings
    assert (ROOT / 'qyunslation/static/qyunslation-logo.png').exists()
    assert (ROOT / 'qyunslation/static/qyunslation-mark.png').exists()


def test_login_callback_does_not_return_to_public_login_route():
    session = (FRONTEND / "src/next/stores/session.js").read_text(encoding="utf-8")

    assert "current.pathname === '/next/login'" in session
    assert "'/next/workbench'" in session
    assert "requestedReturnTo" in session


def test_fastapi_keeps_legacy_root_and_adds_next_surface():
    app = (ROOT / "qyunslation/app.py").read_text(encoding="utf-8")
    assert 'async def main_page()' in app
    assert 'async def next_app_page' in app
    assert '"/app-assets"' in app
