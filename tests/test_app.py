# SPDX-License-Identifier: MPL-2.0
"""轻量 API 烟囱测试（不依赖外部 LLM）。"""
from fastapi.testclient import TestClient


def test_meta_endpoint():
    from qyunslation.app import app

    client = TestClient(app)
    r = client.get("/service/meta")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body


def test_default_params_endpoint():
    from qyunslation.app import app

    client = TestClient(app)
    r = client.get("/service/default-params")
    assert r.status_code == 200
    body = r.json()
    assert "concurrent" in body or "model_id" in body or isinstance(body, dict)


def test_glossary_mounted():
    from qyunslation.app import app

    client = TestClient(app)
    r = client.get("/service/glossary")
    assert r.status_code == 200
    assert "glossary" in r.json()
