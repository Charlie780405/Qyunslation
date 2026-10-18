"""Shared fixtures for PLAN-078a tests: drive a real run through the fake PDF CLI to QA."""
from __future__ import annotations

import stat
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base

pymupdf = pytest.importorskip("pymupdf")

BODY = [
    "The study evaluates the efficacy and safety of the drug in adults with disease",
    "Patients were randomized to receive treatment or placebo for sixteen weeks total",
    "Adverse events were recorded at every scheduled visit during the study period",
    "Primary endpoint was the proportion of patients achieving clear or almost clear",
    "Secondary endpoints included itch numeric rating scale and quality of life data",
]

OWNER = {"X-Dev-User": "own", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
REVIEWER = {"X-Dev-User": "rev", "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}
ADMIN = {"X-Dev-User": "adm", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin,reviewer"}


class EmptyStructuredTermProvider:
    available = True

    def translate(self, source, *, system=None):
        return "[]"


class UnavailableTermProvider:
    def translate(self, source, *, system=None):
        raise RuntimeError("term model unavailable")


class SwitchableTermProvider:
    """Term model whose availability a test can flip between QA rounds."""

    def __init__(self, available: bool = True):
        self.available = available

    def translate(self, source, *, system=None):
        if not self.available:
            raise RuntimeError("term model unavailable")
        return "[]"


def write_cli(path: Path, *, translate: bool) -> None:
    body = (
        "import pathlib, sys, pymupdf\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--output') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        "src = pathlib.Path(args[-1])\n"
        "doc = pymupdf.open(str(src))\n"
    )
    if translate:
        body += (
            "for page in doc:\n"
            "    page.add_redact_annot(page.rect); page.apply_redactions()\n"
            "    for i in range(5):\n"
            "        page.insert_text((72, 100 + 20 * i), '这是第%d行中文译文，包含剂量说明。' % i, fontname='china-s', fontsize=11)\n"
        )
    body += "doc.save(str(out / (src.stem + '.pdf'))); doc.save(str(out / (src.stem + '_dual.pdf')))\n"
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_client(monkeypatch, tmp_path: Path, *, translate: bool, provider=None, db_url: str = "sqlite+pysqlite:///:memory:"):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", db_url)
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    cli = tmp_path / "cli"
    write_cli(cli, translate=translate)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    provider = provider if provider is not None else EmptyStructuredTermProvider()
    # Every route to a model (internal Qwen, DeepSeek, legacy gateway slot) yields the stub.
    monkeypatch.setattr("qyunslation.gateway.provider.get_provider", lambda **_k: provider)
    monkeypatch.setattr("qyunslation.gateway.provider.get_profile_provider", lambda *a, **k: provider)
    Base.metadata.create_all(init_engine(db_url))
    app = FastAPI()
    app.include_router(api_v1_router)
    return TestClient(app)


def source_pdf(tmp_path: Path) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(BODY):
        page.insert_text((72, 100 + 20 * i), line, fontsize=11)
    path = tmp_path / "src.pdf"
    doc.save(str(path))
    return path.read_bytes()


def run_to_gate(client, headers, tmp_path, key, **body):
    """Create a run and poll until QA has produced a verdict."""
    pf = client.post(
        "/api/v1/preflights",
        headers=headers,
        files={"file": ("p.pdf", source_pdf(tmp_path), "application/pdf")},
    ).json()
    run = client.post(
        "/api/v1/translation-runs",
        headers={**headers, "Idempotency-Key": key},
        json={"preflight_id": pf["id"], **body},
    ).json()
    state = run
    for _ in range(300):
        time.sleep(0.05)
        state = client.get(f"/api/v1/translation-runs/{run['id']}", headers=headers).json()
        if state["quality_state"] not in {"draft"}:
            break
    return run["id"], state
