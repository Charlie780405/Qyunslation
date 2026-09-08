from __future__ import annotations

from pathlib import Path

from qyunslation.structure.models import ExecutionStatus, ObjectType
from qyunslation.structure.scan_pdf import PdfStructureScanner


ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"


def _ids(manifest, object_type: ObjectType) -> set[str]:
    return {
        item.semantic_id
        for item in manifest.objects
        if item.type is object_type and item.semantic_id
    }


def test_ljae439_manifest_is_five_figures_three_tables():
    first = PdfStructureScanner().scan(LJAE)
    second = PdfStructureScanner().scan(LJAE)
    assert first.summary.figure_count == 5
    assert first.summary.table_count == 3
    assert _ids(first, ObjectType.FIGURE) == {
        "figure:1",
        "figure:2",
        "figure:3",
        "figure:4",
        "figure:5",
    }
    assert _ids(first, ObjectType.TABLE) == {"table:1", "table:2", "table:3"}
    for item in first.objects:
        if item.type in {ObjectType.FIGURE, ObjectType.TABLE}:
            assert item.detector_evidence
            assert item.detector_evidence[0].bbox is not None
            assert item.caption_ids
    assert first.manifest_id == second.manifest_id
    assert [o.object_id for o in first.objects] == [o.object_id for o in second.objects]


def test_nature_manifest_is_seven_figures_three_tables():
    manifest = PdfStructureScanner().scan(NATURE)
    assert manifest.summary.figure_count == 7
    assert manifest.summary.table_count == 3
    assert _ids(manifest, ObjectType.FIGURE) == {
        f"figure:{n}" for n in range(1, 8)
    }
    pending = [
        item
        for item in manifest.objects
        if item.type is ObjectType.FIGURE
        and item.execution_status is ExecutionStatus.PENDING
    ]
    assert len(pending) == 7
    assert manifest.extensions["translatable_figure_count"] == 7
