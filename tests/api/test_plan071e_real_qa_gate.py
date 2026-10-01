# SPDX-License-Identifier: MPL-2.0
"""PLAN-071e：真实 QA 输入驱动门禁（未翻译产物不得批准）。"""
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


def _cli(path: Path, *, translate: bool) -> None:
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


def _make_client(monkeypatch, tmp_path: Path, *, translate: bool):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    cli = tmp_path / "cli"
    _cli(cli, translate=translate)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    return TestClient(app)


def _source_pdf(tmp_path: Path) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(BODY):
        page.insert_text((72, 100 + 20 * i), line, fontsize=11)
    path = tmp_path / "src.pdf"
    doc.save(str(path))
    return path.read_bytes()


def _run_to_review(client, headers, tmp_path, key):
    pf = client.post(
        "/api/v1/preflights",
        headers=headers,
        files={"file": ("p.pdf", _source_pdf(tmp_path), "application/pdf")},
    ).json()
    run = client.post(
        "/api/v1/translation-runs",
        headers={**headers, "Idempotency-Key": key},
        json={"preflight_id": pf["id"]},
    ).json()
    state = run
    for _ in range(300):
        time.sleep(0.05)
        state = client.get(f"/api/v1/translation-runs/{run['id']}", headers=headers).json()
        if state["quality_state"] in {"review_ready", "qa_blocked"}:
            break
    return run["id"], state


HEADERS = {"X-Dev-User": "qa", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin,reviewer"}


def test_untranslated_output_is_qa_blocked_and_cannot_be_approved(monkeypatch, tmp_path):
    with _make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = _run_to_review(client, HEADERS, tmp_path, "untranslated")
        assert state["quality_state"] == "qa_blocked", state["quality_state"]
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=HEADERS).json()
        assert "UNTRANSLATED_BODY" in {i["code"] for i in items["items"]}
        denied = client.post(
            f"/api/v1/translation-runs/{run_id}/review-decision",
            headers=HEADERS,
            json={"decision": "approve"},
        )
        assert denied.status_code == 409
        final = client.get(f"/api/v1/translation-runs/{run_id}", headers=HEADERS).json()
        assert final["status"] != "succeeded"
        assert not [a for a in final.get("artifacts") or [] if a["formal_export"]]
    reset_engine()


def test_translated_output_reaches_review_ready_without_blockers(monkeypatch, tmp_path):
    with _make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = _run_to_review(client, HEADERS, tmp_path, "translated")
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=HEADERS).json()
        blockers = [i for i in items["items"] if i["severity"] == "blocker"]
        assert state["quality_state"] == "review_ready", (state["quality_state"], blockers)
        codes = {i["code"] for i in items["items"]}
        assert "QA_INSPECTION_SUMMARY" in codes
        assert "TERM_SNAPSHOT_PENDING" not in codes
        run = client.get(f"/api/v1/translation-runs/{run_id}", headers=HEADERS).json()
        assert run["term_summary"]["status"] == "ready"
        assert run["term_summary"]["content_hash"]
    reset_engine()


def test_new_termbase_entries_do_not_rewrite_existing_run_snapshot(monkeypatch, tmp_path):
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.concept_repo import create_staging_concept

    with _make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, _ = _run_to_review(client, HEADERS, tmp_path, "snapshot-frozen")
        before = client.get(f"/api/v1/translation-runs/{run_id}", headers=HEADERS).json()["term_summary"]
        with persist_db.SessionLocal() as session:
            concept = create_staging_concept(
                session, preferred_source="adults", preferred_target="成人", layer="tenant"
            )
            concept.status = "curated"
            session.commit()
        after = client.get(f"/api/v1/translation-runs/{run_id}", headers=HEADERS).json()["term_summary"]
        assert after["content_hash"] == before["content_hash"]
        assert after["termbase_version"] == before["termbase_version"]
    reset_engine()
