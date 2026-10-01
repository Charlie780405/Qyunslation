# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import pytest

from qyunslation.gateway.provider import get_profile_provider


def test_term_deepseek_profile_uses_deepseek_endpoint(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_MODEL", raising=False)
    provider = get_profile_provider("term-deepseek-flash")
    assert provider.base_url.rstrip("/").endswith("api.deepseek.com")
    assert provider.model_id == "deepseek-chat"
    assert provider.api_key == "test-key"


def test_term_deepseek_requires_api_key(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="deepseek not configured"):
        get_profile_provider("term-deepseek-flash")
