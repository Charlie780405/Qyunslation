# SPDX-License-Identifier: MPL-2.0
"""custom_api 术语表端点单元测试（FastAPI TestClient，不启动真实服务）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import glossary_db
from fastapi import FastAPI
from fastapi.testclient import TestClient

from docutranslate.custom_api import router

app = FastAPI()
app.include_router(router, prefix="/service")
client = TestClient(app)


def test_get_glossary(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    r = client.get("/service/glossary")
    assert r.status_code == 200
    body = r.json()
    assert "glossary" in body and "count" in body
    assert body["count"] >= len(glossary_db.PRESET_GLOSSARY)


def test_add_and_delete_glossary(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    # 添加
    r = client.post("/service/glossary", json={"src": "test_term", "dst": "测试术语"})
    assert r.json()["ok"] is True
    # 确认已加入
    r = client.get("/service/glossary")
    assert "test_term" in r.json()["glossary"]
    # 删除
    r = client.delete("/service/glossary/test_term")
    assert r.json()["ok"] is True
    # 确认已删除
    r = client.get("/service/glossary")
    assert "test_term" not in r.json()["glossary"]


def test_add_glossary_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_db, "DB_PATH", tmp_path / "glossary_db.json")
    r = client.post("/service/glossary", json={"src": "", "dst": ""})
    assert r.status_code == 400
