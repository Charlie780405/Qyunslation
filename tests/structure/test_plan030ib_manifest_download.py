from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.structure import ManifestStore, PdfStructureScanner
from qyunslation.structure.models import DocumentStructureManifest

ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
sys.path.insert(0, str(ROOT / "scripts"))
from doc_image_prescan import scan_pdf_tier3  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path / "manifests"))


def test_tier3_result_carries_manifest_metadata():
    if not LJAE.is_file():
        pytest.skip("ljae439 reference fixture missing")
    result = scan_pdf_tier3(LJAE)
    assert result.error is None
    assert result.source_sha256
    assert result.content_profile
    assert result.manifest_json
    manifest = DocumentStructureManifest.model_validate_json(result.manifest_json)
    assert manifest.document.source_sha256 == result.source_sha256


def test_manifest_api_returns_cached_manifest():
    if not LJAE.is_file():
        pytest.skip("ljae439 reference fixture missing")
    digest = hashlib.sha256(LJAE.read_bytes()).hexdigest()
    store = ManifestStore()
    manifest = PdfStructureScanner().scan(LJAE)
    store.put(manifest)

    from qyunslation.custom_api import router

    app = FastAPI()
    app.include_router(router, prefix="/service")
    client = TestClient(app)
    response = client.get(f"/service/manifest/{digest}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["source_sha256"] == digest
    assert "table_fidelity" in payload
    assert "summary_text" in payload["table_fidelity"]
