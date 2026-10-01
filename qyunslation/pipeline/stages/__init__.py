# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：流水线阶段骨架。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qyunslation.pipeline.events import StageEventBuffer
from qyunslation.structure.models import (
    CURRENT_SCHEMA_VERSION,
    AssetRef,
    AssetRole,
    BoundingBox,
    Canvas,
    CanvasKind,
    ContentProfile,
    CoordinateUnit,
    DocumentInfo,
    DocumentStructureManifest,
    LayoutMode,
    ObjectType,
    OutputEditability,
    PreserveKind,
    ProcessingMode,
    ProducerInfo,
    ProfileSource,
    Representation,
    SourceFormat,
    SourceRef,
    SourceRefKind,
    BodyObject,
    ExecutionStatus,
    build_manifest_id,
    build_object_id,
)


@dataclass
class StageResult:
    stage: str
    state: str  # completed | skipped
    message: str = ""
    payload: dict[str, Any] | None = None


def run_validation(*, source_path: Path, source_format: str, events: StageEventBuffer) -> StageResult:
    events.emit("validation", "running", message="validating input")
    if not source_path.is_file():
        events.emit("validation", "failed", message="source missing")
        raise FileNotFoundError(str(source_path))
    events.emit("validation", "completed", message=f"format={source_format}")
    return StageResult(stage="validation", state="completed")


def _source_format_enum(source_format: str) -> SourceFormat:
    key = source_format.strip().upper()
    aliases = {
        "JPG": "JPEG",
        "JPEG": "JPEG",
        "PNG": "PNG",
        "PDF": "PDF",
        "DOCX": "DOCX",
        "PPTX": "PPTX",
    }
    name = aliases.get(key, key)
    try:
        return SourceFormat(name)
    except ValueError:
        return SourceFormat.UNKNOWN


def build_minimal_manifest(
    *,
    source_sha256: str,
    source_name: str,
    source_format: str,
    page_or_slide_count: int = 1,
) -> DocumentStructureManifest:
    """Build a Manifest 2.0 skeleton usable before full scanners run."""
    fmt = _source_format_enum(source_format)
    canvas_kind = CanvasKind.SLIDE if fmt is SourceFormat.PPTX else CanvasKind.PAGE
    canvases: list[Canvas] = []
    objects: list[Any] = []
    reverse_index: dict[str, str] = {}
    for index in range(1, max(1, page_or_slide_count) + 1):
        canvas_id = f"{'slide' if canvas_kind is CanvasKind.SLIDE else 'page'}:{index}"
        canvases.append(
            Canvas(
                canvas_id=canvas_id,
                kind=canvas_kind,
                source_index=index,
                width=612,
                height=792,
                unit=CoordinateUnit.PT,
                rotation=0,
                layout_mode=LayoutMode.SINGLE,
            )
        )
        semantic_key = f"body:{index}"
        object_id = build_object_id(
            source_sha256,
            canvas_id,
            ObjectType.BODY,
            semantic_key,
            [{"kind": "GENERATED_ASSET", "ref": semantic_key}],
        )
        objects.append(
            BodyObject(
                type=ObjectType.BODY,
                object_id=object_id,
                canvas_id=canvas_id,
                bbox=BoundingBox(x0=36, y0=36, x1=576, y1=756),
                representation=Representation.NATIVE_TEXT,
                source_refs=[
                    SourceRef(kind=SourceRefKind.GENERATED_ASSET, ref=semantic_key, occurrence_index=1)
                ],
                execution_status=ExecutionStatus.PENDING,
                reading_order=index,
                preserve_kind=PreserveKind.NONE,
                source_object_hash=None,
            )
        )
        reverse_index[f"{canvas_id}:body"] = object_id

    created = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    manifest = DocumentStructureManifest(
        schema_version=CURRENT_SCHEMA_VERSION,
        manifest_id=build_manifest_id(source_sha256, CURRENT_SCHEMA_VERSION),
        created_at=created,
        producer=ProducerInfo(name="qyunslation.pipeline", version="071b"),
        document=DocumentInfo(
            source_sha256=source_sha256,
            source_name=source_name,
            source_format=fmt,
            detected_mime="application/octet-stream",
            content_profile=ContentProfile.GENERIC,
            profile_source=ProfileSource.AUTO,
            profile_confidence=0.0,
            profile_evidence=["pipeline-skeleton"],
            requested_mode=ProcessingMode.NATIVE,
            selected_mode=ProcessingMode.NATIVE,
            output_editability=OutputEditability.EDITABLE,
            input_asset=AssetRef(
                asset_id="source",
                role=AssetRole.INPUT,
                sha256=source_sha256,
                media_type="application/octet-stream",
                locator=f"sealed:{source_sha256}",
            ),
        ),
        canvases=canvases,
        objects=objects,
        reverse_index=reverse_index,
        extensions={"graphics_inventory": [], "pipeline": "071b"},
    )
    return manifest.refresh_summary()


def run_structure(
    *,
    source_path: Path,
    source_format: str,
    source_sha256: str,
    events: StageEventBuffer,
) -> tuple[StageResult, DocumentStructureManifest]:
    events.emit("structure", "running", message="building manifest")
    fmt = source_format.casefold()
    manifest: DocumentStructureManifest | None = None
    try:
        if fmt == "pdf":
            from qyunslation.structure.scan_pdf import PdfStructureScanner

            scanned = PdfStructureScanner().scan(source_path)
            # Re-serialize through model to attach v2 defaults when possible.
            data = scanned.model_dump(mode="json")
            data["schema_version"] = CURRENT_SCHEMA_VERSION
            data["manifest_id"] = build_manifest_id(source_sha256, CURRENT_SCHEMA_VERSION)
            data.setdefault("reverse_index", {})
            for obj in data.get("objects") or []:
                obj.setdefault("preserve_kind", "none")
            manifest = DocumentStructureManifest.model_validate(data).refresh_summary()
        elif fmt == "docx":
            from qyunslation.structure.scan_docx import DocxStructureScanner

            scanned = DocxStructureScanner().scan(source_path)
            data = scanned.model_dump(mode="json")
            data["schema_version"] = CURRENT_SCHEMA_VERSION
            data["manifest_id"] = build_manifest_id(
                data["document"]["source_sha256"], CURRENT_SCHEMA_VERSION
            )
            data.setdefault("reverse_index", {})
            manifest = DocumentStructureManifest.model_validate(data).refresh_summary()
        elif fmt == "pptx":
            from qyunslation.structure.scan_pptx import PptxStructureScanner

            scanned = PptxStructureScanner().scan(source_path)
            data = scanned.model_dump(mode="json")
            data["schema_version"] = CURRENT_SCHEMA_VERSION
            data["manifest_id"] = build_manifest_id(
                data["document"]["source_sha256"], CURRENT_SCHEMA_VERSION
            )
            data.setdefault("reverse_index", {})
            manifest = DocumentStructureManifest.model_validate(data).refresh_summary()
        elif fmt in {"png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "gif"}:
            from qyunslation.structure.scan_image import ImageStructureScanner

            scanned = ImageStructureScanner().scan(source_path)
            data = scanned.model_dump(mode="json")
            data["schema_version"] = CURRENT_SCHEMA_VERSION
            data["manifest_id"] = build_manifest_id(
                data["document"]["source_sha256"], CURRENT_SCHEMA_VERSION
            )
            data.setdefault("reverse_index", {})
            manifest = DocumentStructureManifest.model_validate(data).refresh_summary()
    except Exception as exc:  # noqa: BLE001 — fall back to skeleton
        events.emit(
            "structure",
            "running",
            message=f"scanner fallback: {type(exc).__name__}",
        )
        manifest = None

    if manifest is None:
        manifest = build_minimal_manifest(
            source_sha256=source_sha256,
            source_name=source_path.name,
            source_format=source_format,
        )
    # Ensure reverse index has at least canvas→first object entries.
    if not manifest.reverse_index:
        for obj in manifest.objects:
            key = f"{obj.canvas_id}:{obj.type.value.lower()}"
            manifest.reverse_index.setdefault(key, obj.object_id)
    events.emit(
        "structure",
        "completed",
        message=f"objects={len(manifest.objects)} version={manifest.schema_version}",
    )
    return StageResult(stage="structure", state="completed"), manifest


def run_ocr_decision(
    *,
    source_format: str,
    scanned_hint: bool,
    events: StageEventBuffer,
) -> StageResult:
    """OCR stage gate: skip for non-PDF / text PDF; mark running intent for scans."""
    events.emit("ocr", "running", message="ocr gate")
    if source_format.casefold() != "pdf":
        events.emit("ocr", "skipped", message="non-pdf")
        return StageResult(stage="ocr", state="skipped", message="non-pdf")
    if scanned_hint:
        # Full HPD execution remains in runner retry / 071c migration.
        events.emit("ocr", "completed", message="scanned pdf — HPD handled by executor")
        return StageResult(stage="ocr", state="completed", message="executor-hpd")
    events.emit("ocr", "skipped", message="text pdf")
    return StageResult(stage="ocr", state="skipped", message="text-pdf")
