# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：embed client 单测（mock HTTP，不断泰州）。"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from qyunslation.embed.client import EmbedError, embed_health, embed_texts


def _http_response(payload: dict, code: int = 200):
    body = json.dumps(payload).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.status = code
    return resp


def test_embed_texts_empty():
    assert embed_texts([]) == []


def test_embed_texts_ok(monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBED_DIM", "4")
    vec = [0.1, 0.2, 0.3, 0.4]
    with patch("urllib.request.urlopen", return_value=_http_response({"embeddings": [vec, vec]})):
        out = embed_texts(["a", "b"])
    assert out == [vec, vec]


def test_embed_texts_dim_mismatch(monkeypatch):
    monkeypatch.setenv("OLLAMA_EMBED_DIM", "4")
    with patch(
        "urllib.request.urlopen",
        return_value=_http_response({"embeddings": [[1.0, 2.0]]}),
    ):
        with pytest.raises(EmbedError, match="dim"):
            embed_texts(["a"])


def test_embed_health_ok():
    with patch(
        "urllib.request.urlopen",
        return_value=_http_response({"models": [{"name": "bge-m3:latest"}]}),
    ):
        h = embed_health()
    assert h["ok"] is True
    assert h["has_bge_m3"] is True


def test_embed_health_unreachable():
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        h = embed_health()
    assert h["ok"] is False
    assert "error" in h
