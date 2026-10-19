# SPDX-License-Identifier: MPL-2.0
"""PLAN-078f f6: the term-suggestion button says where the snippets go before anyone clicks it."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base
from qyunslation.workbench.term_extract import term_suggester_info

HEADERS = {"X-Dev-User": "reviewer", "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}


def _run(classification="internal", term_profile=""):
    return SimpleNamespace(
        document_classification=classification,
        settings_snapshot={"term_model_profile_id": term_profile} if term_profile else {},
    )


def test_confidential_material_never_shows_an_external_term_model(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DEEPSEEK_API_KEY", "x")
    info = term_suggester_info(_run("confidential", "term-deepseek-flash"))
    assert info["profile_id"] == "term-internal-qwen" and info["egress_scope"] == "none"


def test_internal_material_with_deepseek_configured_says_snippets_leave_the_network(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DEEPSEEK_API_KEY", "x")
    info = term_suggester_info(_run("internal"))
    assert info["provider"] == "deepseek" and info["egress_scope"] == "redacted_term_snippets"
    assert "DeepSeek" in info["label"]


def test_without_an_external_key_the_default_is_the_in_house_model(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert term_suggester_info(_run("internal"))["egress_scope"] == "none"


def test_a_choice_recorded_on_the_run_wins(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_API_KEY", raising=False)
    info = term_suggester_info(_run("internal", "term-internal-qwen"))
    assert info["profile_id"] == "term-internal-qwen" and info["egress_scope"] == "none"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    from qyunslation.api import v1 as api_v1_module

    async def _no_launch(*, run, preflight, target_language, **_kwargs):
        run.status = "failed"
        run.stage = "qa"

    monkeypatch.setattr(api_v1_module, "_launch_translation_run", _no_launch)
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def test_the_candidate_listing_carries_the_suggester_and_listing_it_calls_nothing(client, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DEEPSEEK_API_KEY", "x")
    called = []
    monkeypatch.setattr(
        "qyunslation.workbench.term_extract.enrich_run_term_suggestions",
        lambda *args, **kwargs: called.append(1) or 0,
    )
    preflight = client.post(
        "/api/v1/preflights", headers=HEADERS,
        files={"file": ("a.txt", b"Dupilumab inhibits IL-4 signaling in adults with atopic dermatitis. " * 4, "text/plain")},
    ).json()
    run = client.post(
        "/api/v1/translation-runs", headers={**HEADERS, "Idempotency-Key": "egress-1"},
        json={"preflight_id": preflight["id"]},
    ).json()
    listing = client.get(f"/api/v1/translation-runs/{run['id']}/term-candidates", headers=HEADERS).json()
    assert listing["suggester"]["egress_scope"] in {"none", "redacted_term_snippets"}
    assert listing["suggester"]["label"]
    assert called == []  # a read never reaches a model
