"""PLAN-030f：图片/Poster 结构扫描与 manifest 闭环。"""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.structure import ImageStructureScanner, ManifestStore
from qyunslation.structure.image_tiles import plan_image_tiles
from qyunslation.structure.models import (
    CanvasKind,
    ContentProfile,
    ExecutionStatus,
    ObjectType,
)
from qyunslation.structure.scan_image import ImageStructureScanner as ScannerClass
from qyunslation.workflow.image_overlay_workflow import ImageOverlayWorkflow, ImageOverlayWorkflowConfig

ROOT = Path(__file__).resolve().parents[2]


def _fixture_ocr(path: Path) -> list[tuple[int, int, int, int, str, float]]:
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
    return [
        (48, 70, 160, 95, "Figure 1", 0.95),
        (width // 2 + 24, 70, width // 2 + 140, 95, "Table 1", 0.94),
        (32, height - 140, width - 32, height - 100, "Methods summary", 0.93),
    ]


@pytest.fixture
def scanner() -> ImageStructureScanner:
    return ScannerClass(ocr_fn=_fixture_ocr)


def test_scan_png_produces_image_with_bbox_and_blocks(
    generated_structure_fixtures: Path, scanner: ImageStructureScanner
):
    path = generated_structure_fixtures / "diagram.webp"
    manifest = scanner.scan(path)

    images = [obj for obj in manifest.objects if obj.type is ObjectType.IMAGE]
    assert len(images) == 1
    image = images[0]
    assert image.bbox is not None
    assert image.bbox.x1 == pytest.approx(320)
    assert len(image.translatable_blocks) >= 2
    assert all(block.bbox is not None for block in image.translatable_blocks)


def test_poster_profile_emits_poster_sections(
    generated_structure_fixtures: Path, scanner: ImageStructureScanner
):
    path = generated_structure_fixtures / "poster.png"
    manifest = scanner.scan(path, content_profile=ContentProfile.POSTER)

    assert manifest.document.content_profile is ContentProfile.POSTER
    assert manifest.canvases[0].kind is CanvasKind.POSTER
    sections = [obj for obj in manifest.objects if obj.type is ObjectType.POSTER_SECTION]
    assert len(sections) >= 2
    assert all(section.bbox is not None for section in sections)
    assert all(section.semantic_id.startswith("poster:section:") for section in sections)
    assert manifest.canvases[0].reading_order


def test_multipage_tiff_emits_one_image_per_frame(
    generated_structure_fixtures: Path, scanner: ImageStructureScanner
):
    path = generated_structure_fixtures / "multipage.tiff"
    manifest = scanner.scan(path)

    assert len(manifest.canvases) == 2
    images = [obj for obj in manifest.objects if obj.type is ObjectType.IMAGE]
    assert len(images) == 2
    assert {image.canvas_id for image in images} == {"page:1", "page:2"}


def test_tile_plan_triggers_for_oversized_canvas():
    tiles = plan_image_tiles(5000, 3000, max_side=2048, overlap=128)
    assert len(tiles) > 1
    assert tiles[0].x0 == 0 and tiles[0].y0 == 0


def test_manifest_store_roundtrip_image(
    generated_structure_fixtures: Path, scanner: ImageStructureScanner, tmp_path, monkeypatch
):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path))
    manifest = scanner.scan(generated_structure_fixtures / "diagram.webp")
    store = ManifestStore()
    assert store.put(manifest) is not None
    loaded = store.get(manifest.document.source_sha256)
    assert loaded is not None
    assert loaded.summary.object_counts.get("IMAGE") == manifest.summary.object_counts.get("IMAGE")


def test_image_overlay_workflow_manifest_none_still_translates(monkeypatch):
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    workflow = ImageOverlayWorkflow(config=ImageOverlayWorkflowConfig())
    workflow.read_bytes(payload, stem="tiny", suffix=".png")
    monkeypatch.setattr(
        workflow,
        "_structure_manifest",
        lambda _doc: None,
    )
    monkeypatch.setattr(
        "qyunslation.extensions.image_translate.translate_image_bytes",
        lambda data, suffix, to_lang: (data, 0, {}),
    )
    workflow.translate()
    assert workflow.document_translated is not None


def test_image_overlay_workflow_writes_execution_status(
    generated_structure_fixtures: Path, scanner: ImageStructureScanner, monkeypatch, tmp_path
):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path))
    path = generated_structure_fixtures / "diagram.webp"
    manifest = scanner.scan(path)
    ManifestStore().put(manifest)
    workflow = ImageOverlayWorkflow(config=ImageOverlayWorkflowConfig())
    workflow.read_bytes(path.read_bytes(), stem="diagram", suffix=".webp")
    monkeypatch.setattr(workflow, "_structure_manifest", lambda _doc: manifest)
    monkeypatch.setattr(
        "qyunslation.extensions.image_translate.translate_image_bytes",
        lambda data, suffix, to_lang: (data, 3, {"graphics_damage": 0}),
    )
    workflow.translate()
    updated = ManifestStore().get_execution(manifest.document.source_sha256)
    assert updated is not None
    images = [obj for obj in updated.objects if obj.type is ObjectType.IMAGE]
    assert images
    assert images[0].execution_status is ExecutionStatus.TRANSLATED
    assert images[0].output_evidence is not None
