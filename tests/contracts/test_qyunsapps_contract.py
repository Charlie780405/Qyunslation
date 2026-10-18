"""qyunslation 的 QyunsApps 边缘 / 身份合同（PLAN-077 T1）。

合同文件 qyunsapps-contract.json 是 qyunslation 一侧的 SSOT；可部署的生产 Caddy 配置与 Authentik 蓝图只在 QyunsApps。
这里把合同与本仓认证代码、前端接线、以及（若本机有）QyunsApps 的边缘站点/蓝图对账。没有网络、没有数据库、没有 secret。
"""
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((Path(__file__).parent / "qyunsapps-contract.json").read_text())
QYUNSAPPS = Path(os.environ.get("QYUNSAPPS_REPO", "/home/dev/QyunsApps"))
EDGE_SITE = QYUNSAPPS / "infra/edge/sites/translate.caddy"
BLUEPRINT = QYUNSAPPS / "authentik/blueprints/qyunslation-oidc.yaml"


def test_contract_has_no_secrets_or_pii():
    raw = json.dumps(CONTRACT).lower()
    for needle in ("secret", "password", "@gmail", "@qq", "begin "):
        assert needle not in raw, needle


def test_bff_matches_the_oidc_contract():
    bff = (ROOT / "qyunslation/auth/bff.py").read_text()
    o = CONTRACT["oidc"]
    assert '"/auth/callback"' in bff and o["redirect_uri"].endswith("/auth/callback")
    assert f'"scope": "{" ".join(o["scopes"])}"' in bff
    assert re.search(rf"_DEFAULT_IDLE_MINUTES = {o['session']['idle_minutes_default']}\b", bff)
    assert re.search(rf"_DEFAULT_ABSOLUTE_HOURS = {o['session']['absolute_hours_default']}\b", bff)
    ident = (ROOT / "qyunslation/persist/identity.py").read_text()
    assert f'WEB_SESSION_COOKIE = "{o["session"]["cookie"]}"' in ident
    assert f'CSRF_COOKIE = "{o["session"]["csrf_cookie"]}"' in ident
    b = CONTRACT["logout"]["bff"]
    assert f'@router.post("{b["path"]}"' in bff and "require_csrf(request)" in bff


def test_logout_allowlist_and_chain_route_match_the_contract():
    lib = (ROOT / "frontend/src/next/qyuns/logout.js").read_text()
    for h in CONTRACT["logout"]["next_hosts"]:
        assert f"'{h}'" in lib, h
    assert CONTRACT["logout"]["chain_route"] in lib
    assert CONTRACT["logout"]["end_session"] in lib
    assert CONTRACT["logout"]["bff"]["csrf_header"] in lib


def test_appbar_integration_matches_the_contract():
    mount = (ROOT / "frontend/src/next/qyuns/appbar-mount.js").read_text()
    assert CONTRACT["appbar"]["current_app"] in mount
    assert f"'{CONTRACT['appbar']['theme']}'" in mount or f'"{CONTRACT["appbar"]["theme"]}"' in mount


def test_legacy_blueprint_is_marked_as_migration_baseline():
    note = (ROOT / "deploy/authentik/blueprints/README.md").read_text()
    assert "QyunsApps" in note and "迁移基线" in note


def test_qyunsapps_edge_site_matches_the_contract_when_available():
    if not EDGE_SITE.exists():
        pytest.skip(f"没有 {EDGE_SITE}（本机无 QyunsApps 仓库，跳过与边缘 SSOT 的对账）")
    edge = EDGE_SITE.read_text()
    assert f"https://{CONTRACT['host']}" in edge
    assert set(re.findall(r"reverse_proxy\s+(127\.0\.0\.1:\d+)", edge)) == set(CONTRACT["upstreams"].values())
    for r in CONTRACT["routes"]:
        for m in re.split(r",\s*", r["match"]):
            if m.startswith("/") and r.get("upstream"):
                assert re.search(rf"path[^\n]*{re.escape(m)}", edge), m
    for t in ("60s", "30s", "120s"):
        assert f"read_timeout {t}" in edge
    for h in CONTRACT["security_headers"]:
        assert h in edge, h
    assert "redir @qyunslation_root /next/ 302" in edge


def test_qyunsapps_blueprint_matches_the_contract_when_available():
    if not BLUEPRINT.exists():
        pytest.skip(f"没有 {BLUEPRINT}")
    bp = BLUEPRINT.read_text()
    o = CONTRACT["oidc"]
    assert f"client_id: {o['client_id']}" in bp
    assert o["redirect_uri"] in bp
    assert o["vue_beta_group"] in bp
    assert "client_secret" not in bp.replace("不含 client_secret", "").replace("client_secret。", "")
