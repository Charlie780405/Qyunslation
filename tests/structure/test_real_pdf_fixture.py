from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qyunslation.structure.canvases import extract_canvases
from qyunslation.structure.ingest import detect_input
from qyunslation.structure.models import CanvasKind, CoordinateUnit, SourceFormat


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
TRUTH = ROOT / "tests/fixtures/structure/ljae439.truth.json"


def test_ljae439_real_pdf_integrity_and_canonical_pages():
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    content = FIXTURE.read_bytes()

    assert truth["usage_scope"] == "TEST_FIXTURE_ONLY"
    assert truth["source"]["runtime_dependency"] is False
    assert hashlib.sha256(content).hexdigest() == truth["source"]["sha256"]

    detected = detect_input(FIXTURE.name, content, declared_mime="application/pdf")
    canvases = extract_canvases(detected.source_format, content)

    assert detected.source_format is SourceFormat.PDF
    assert len(canvases) == 10
    assert [canvas.canvas_id for canvas in canvases] == [
        f"page:{index}" for index in range(1, 11)
    ]
    assert all(canvas.kind is CanvasKind.PAGE for canvas in canvases)
    assert all(canvas.unit is CoordinateUnit.PT for canvas in canvases)
    assert all(canvas.width == pytest.approx(595.276) for canvas in canvases)
    assert all(canvas.height == pytest.approx(782.362) for canvas in canvases)


def test_production_package_has_no_knowledge_base_fixture_dependency():
    forbidden = ("ljae439", ".hermes/attachments", "knowledge-base://")
    for source in (ROOT / "qyunslation").rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden), source
