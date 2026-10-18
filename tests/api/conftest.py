"""API tests never reach a real model endpoint.

pytest-env points DOCUTRANSLATE_BASE_URL at api.openai.com, and since PLAN-078a every run
has a default term model, so an unpatched test would make a live HTTP call. Tests that
need a model install their own stub over this one.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_term_model(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("no live model in API tests; install a stub provider")

    monkeypatch.setattr("qyunslation.gateway.provider.get_profile_provider", unavailable)
