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
    styles = (FRONTEND / "src/next/next.css").read_text(encoding="utf-8")

    for route in ("/login", "/workbench", "/termbase", "/settings"):
        assert route in router
    assert "Qyunslation" in shell
    assert "--qy-primary: #005076" in styles
    assert "--qy-brand-green: #81BB39" in styles


def test_fastapi_keeps_legacy_root_and_adds_next_surface():
    app = (ROOT / "qyunslation/app.py").read_text(encoding="utf-8")
    assert 'async def main_page()' in app
    assert 'async def next_app_page' in app
    assert '"/app-assets"' in app
