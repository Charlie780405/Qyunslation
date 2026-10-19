"""PLAN-078c: what is confirmed == what the server resolved == what is frozen == what the executor gets."""
from __future__ import annotations

import json
import stat
import time
from pathlib import Path

import pytest

from _plan078_flow import ADMIN, make_client, source_pdf
from qyunslation.persist.db import reset_engine

pytest.importorskip("pymupdf")

# The fake CLI records exactly the arguments it was started with, then writes a translated PDF.
DUMPING_CLI = """#!/usr/bin/env python3
import json, os, pathlib, sys, pymupdf
args = sys.argv[1:]
pathlib.Path(os.environ["QY_ARGV_DUMP"]).write_text(json.dumps(args), encoding="utf-8")
out = pathlib.Path(args[args.index('--output') + 1]); out.mkdir(parents=True, exist_ok=True)
src = pathlib.Path(args[-1])
doc = pymupdf.open(str(src))
for page in doc:
    page.add_redact_annot(page.rect); page.apply_redactions()
    for i in range(5):
        page.insert_text((72, 100 + 20 * i), '这是第%d行中文译文。' % i, fontname='china-s', fontsize=11)
doc.save(str(out / (src.stem + '.pdf')))
"""

CASES = [
    {"bilingual": True},
    {"bilingual": False},
    {"bilingual": False, "source_language": "简体中文", "target_language": "English"},
    {"document_classification": "confidential", "profile": "监管申报材料"},
]


@pytest.mark.parametrize("variant", CASES, ids=lambda v: ",".join(f"{k}={v[k]}" for k in v))
def test_confirmed_resolved_frozen_and_executed_configuration_agree(monkeypatch, tmp_path: Path, variant):
    dump = tmp_path / "argv.json"
    monkeypatch.setenv("QY_ARGV_DUMP", str(dump))
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        cli = tmp_path / "cli"
        cli.write_text(DUMPING_CLI, encoding="utf-8")
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)

        pf = client.post(
            "/api/v1/preflights", headers=ADMIN, files={"file": ("p.pdf", source_pdf(tmp_path), "application/pdf")}
        ).json()
        body = {"preflight_id": pf["id"], **variant}

        # 1. what the person is shown and confirms
        validated = client.post("/api/v1/translation-runs/validate", headers=ADMIN, json=body).json()
        assert validated["ok"], validated["errors"]
        shown = validated["config"]

        # 2. what is submitted, carrying the confirmed digest
        created = client.post(
            "/api/v1/translation-runs",
            headers={**ADMIN, "Idempotency-Key": "contract"},
            json={**body, "config_digest": validated["config_digest"]},
        )
        assert created.status_code == 201, created.text
        run = created.json()
        frozen = run["settings"]

        # shown == frozen
        assert frozen["config_digest"] == validated["config_digest"]
        assert frozen["direction"] == shown["direction"]
        assert frozen["source_language"] == shown["source_language"]
        assert frozen["target_language"] == shown["target_language"]
        assert frozen["profile"] == shown["profile"]
        assert frozen["domain_profile"] == shown["domain_profile"]
        assert frozen["document_classification"] == shown["document_classification"]
        assert frozen["model_profile_id"] == shown["model_profile_id"]
        assert frozen["term_model_profile_id"] == shown["term_model_profile_id"]
        assert frozen["bilingual"] == shown["bilingual"]
        assert frozen["bilingual_effective"] == shown["bilingual_effective"]
        assert frozen["model_snapshot"]["egress_scope"] == shown["egress_scope"]
        assert run["document_classification"] == shown["document_classification"]
        assert run["model_profile_id"] == shown["model_profile_id"]

        # 3. what the executor was actually started with
        deadline = time.time() + 20
        while not dump.exists() and time.time() < deadline:
            client.get(f"/api/v1/translation-runs/{run['id']}", headers=ADMIN)
            time.sleep(0.05)
        argv = json.loads(dump.read_text(encoding="utf-8"))
        codes = {"English": "en", "简体中文": "zh"}
        assert argv[argv.index("--lang-in") + 1] == codes[shown["source_language"]]
        assert argv[argv.index("--lang-out") + 1] == codes[shown["target_language"]]
        assert ("--no-dual" in argv) == (not shown["bilingual_effective"])

        # and the frozen record is what later steps read: a revision keeps it unless told otherwise
        again = client.get(f"/api/v1/translation-runs/{run['id']}", headers=ADMIN).json()
        assert again["settings"]["config_digest"] == validated["config_digest"]
    reset_engine()
