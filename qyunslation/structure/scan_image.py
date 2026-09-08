# SPDX-License-Identifier: MPL-2.0
"""PLAN-030f：独立图片/Poster 结构扫描。"""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from .image_tiles import (
    DEFAULT_TILE_MAX_SIDE,
    DEFAULT_TILE_MEMORY_BUDGET_PX,
    detect_tile_seam_overlaps,
    plan_image_tiles,
    tile_memory_pixels,
)
from .ingest import prepare_document
from .models import (
    BoundingBox,
    CanvasKind,
    ContentProfile,
    DetectorEvidence,
    DocumentInfo,
    DocumentStructureManifest,
    ExecutionStatus,
    ImageObject,
    IssueSeverity,
    ManifestIssue,
    ObjectType,
    OutputEditability,
    PipelineStage,
    PosterSectionObject,
    ProcessingMode,
    ProducerInfo,
    ProfileSource,
    Representation,
    SourceFormat,
    SourceRef,
    SourceRefKind,
    TranslatableBlock,
    build_manifest_id,
    build_object_id,
    CURRENT_SCHEMA_VERSION,
)
from .profiles import resolve_profile

OcrBox = tuple[int, int, int, int, str, float]
OcrFn = Callable[[Path], list[OcrBox]]

_IMAGE_FORMATS = {
    SourceFormat.PNG,
    SourceFormat.JPEG,
    SourceFormat.WEBP,
    SourceFormat.BMP,
    SourceFormat.TIFF,
    SourceFormat.GIF,
    SourceFormat.HEIF,
    SourceFormat.HEIC,
    SourceFormat.AVIF,
}

_POSTER_PROFILES = {ContentProfile.POSTER}


def _bbox(x0: int, y0: int, x1: int, y1: int) -> BoundingBox:
    return BoundingBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))


def _full_canvas_bbox(width: float, height: float) -> BoundingBox:
    return BoundingBox(x0=0.0, y0=0.0, x1=float(width), y1=float(height))


def _default_ocr(path: Path) -> list[OcrBox]:
    from qyunslation.extensions.image_translate import ocr_image

    return ocr_image(path)


def _ocr_boxes(content: bytes, suffix: str, ocr_fn: OcrFn, *, frame_index: int = 0) -> list[OcrBox]:
    payload = _frame_bytes(content, suffix, frame_index)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(payload)
        handle.flush()
        return ocr_fn(Path(handle.name))


def _frame_bytes(content: bytes, suffix: str, frame_index: int) -> bytes:
    from PIL import Image

    with Image.open(BytesIO(content)) as image:
        if frame_index > 0:
            image.seek(frame_index)
        if int(getattr(image, "n_frames", 1)) <= 1 and frame_index == 0:
            return content
        out = BytesIO()
        image.save(out, format=image.format or "PNG")
        return out.getvalue()


def _blocks_from_boxes(boxes: list[OcrBox]) -> list[TranslatableBlock]:
    blocks: list[TranslatableBlock] = []
    for index, (x0, y0, x1, y1, text, score) in enumerate(boxes):
        stripped = (text or "").strip()
        if not stripped:
            continue
        blocks.append(
            TranslatableBlock(
                block_id=f"block:{index}",
                source_text=stripped,
                bbox=_bbox(x0, y0, x1, y1),
                source_language=None,
            )
        )
    return blocks


def _poster_sections(
    boxes: list[OcrBox],
    canvas_width: float,
    canvas_height: float,
) -> list[tuple[BoundingBox, list[TranslatableBlock]]]:
    """Partition OCR blocks into vertical poster sections by spatial gaps."""
    if not boxes:
        mid = canvas_height / 2.0
        return [
            (
                BoundingBox(x0=0.0, y0=0.0, x1=canvas_width, y1=mid),
                [],
            ),
            (
                BoundingBox(x0=0.0, y0=mid, x1=canvas_width, y1=canvas_height),
                [],
            ),
        ]

    sorted_boxes = sorted(boxes, key=lambda item: (item[1], item[0]))
    groups: list[list[OcrBox]] = [[sorted_boxes[0]]]
    gap_threshold = max(48.0, canvas_height * 0.08)
    for box in sorted_boxes[1:]:
        prev = groups[-1][-1]
        if box[1] - prev[3] > gap_threshold:
            groups.append([box])
        else:
            groups[-1].append(box)

    sections: list[tuple[BoundingBox, list[TranslatableBlock]]] = []
    for group_index, group in enumerate(groups, start=1):
        x0 = min(item[0] for item in group)
        y0 = min(item[1] for item in group)
        x1 = max(item[2] for item in group)
        y1 = max(item[3] for item in group)
        pad = 16.0
        section_bbox = BoundingBox(
            x0=max(0.0, x0 - pad),
            y0=max(0.0, y0 - pad),
            x1=min(canvas_width, x1 + pad),
            y1=min(canvas_height, y1 + pad),
        )
        section_blocks = [
            TranslatableBlock(
                block_id=f"section:{group_index}:block:{idx}",
                source_text=item[4].strip(),
                bbox=_bbox(item[0], item[1], item[2], item[3]),
            )
            for idx, item in enumerate(group)
            if item[4].strip()
        ]
        sections.append((section_bbox, section_blocks))
    return sections


def _upgrade_canvas_for_poster(canvas) -> None:
    if canvas.kind is CanvasKind.POSTER:
        return
    canvas.kind = CanvasKind.POSTER
    canvas.canvas_id = f"poster:{canvas.source_index}"


class ImageStructureScanner:
    """Produce a validated manifest from PNG/JPEG/WebP/BMP/TIFF and poster inputs."""

    def __init__(self, *, ocr_fn: OcrFn | None = None) -> None:
        self._ocr_fn = ocr_fn or _default_ocr

    def scan(
        self,
        source: Path | str | bytes,
        *,
        source_name: str = "image.png",
        content_profile: ContentProfile | None = None,
    ) -> DocumentStructureManifest:
        if isinstance(source, (Path, str)):
            path = Path(source)
            content = path.read_bytes()
            source_name = path.name
        else:
            content = bytes(source)

        prepared = prepare_document(source_name, content)
        if prepared.source_format not in _IMAGE_FORMATS:
            raise ValueError(
                f"ImageStructureScanner expects raster image, got {prepared.source_format}"
            )

        suffix = Path(source_name).suffix or ".png"
        issues: list[ManifestIssue] = []
        objects: list = []
        frame_boxes: dict[int, list[OcrBox]] = {}

        for canvas in prepared.canvases:
            if content_profile in _POSTER_PROFILES:
                _upgrade_canvas_for_poster(canvas)

            frame_index = canvas.source_index - 1
            if frame_index not in frame_boxes:
                frame_boxes[frame_index] = _ocr_boxes(
                    content, suffix, self._ocr_fn, frame_index=frame_index
                )
            boxes = frame_boxes[frame_index]

            width = int(canvas.width)
            height = int(canvas.height)
            tiles = plan_image_tiles(width, height, max_side=DEFAULT_TILE_MAX_SIDE)
            tile_pixels = tile_memory_pixels(tiles)
            if len(tiles) > 1:
                if tile_pixels > DEFAULT_TILE_MEMORY_BUDGET_PX:
                    issues.append(
                        ManifestIssue(
                            code="IMAGE_TILE_MEMORY_BUDGET_EXCEEDED",
                            severity=IssueSeverity.WARNING,
                            stage=PipelineStage.SCAN,
                            message="图片分块内存预算超限，将 fail-soft 整图处理",
                            details={
                                "canvas_id": canvas.canvas_id,
                                "tile_count": len(tiles),
                                "tile_pixels": tile_pixels,
                            },
                        )
                    )
                for left, right in zip(tiles, tiles[1:]):
                    left_blocks = [
                        (b[0], b[1], b[2], b[3], b[4])
                        for b in boxes
                        if b[0] >= left.x0 and b[2] <= left.x1
                    ]
                    right_blocks = [
                        (b[0], b[1], b[2], b[3], b[4])
                        for b in boxes
                        if b[0] >= right.x0 and b[2] <= right.x1
                    ]
                    for warning in detect_tile_seam_overlaps(
                        left_blocks,
                        right_blocks,
                        overlap_px=right.x0 - left.x0 if right.x0 > left.x0 else 0,
                    ):
                        issues.append(
                            ManifestIssue(
                                code="IMAGE_TILE_SEAM_WARNING",
                                severity=IssueSeverity.INFO,
                                stage=PipelineStage.SCAN,
                                message=warning,
                                details={"canvas_id": canvas.canvas_id},
                            )
                        )

            blocks = _blocks_from_boxes(boxes)
            reading_order: list[str] = []
            canvas_bbox = _full_canvas_bbox(canvas.width, canvas.height)

            if canvas.kind is CanvasKind.POSTER:
                for section_index, (section_bbox, section_blocks) in enumerate(
                    _poster_sections(boxes, canvas.width, canvas.height),
                    start=1,
                ):
                    key = f"poster:section:{section_index}"
                    object_id = build_object_id(
                        prepared.source_sha256,
                        canvas.canvas_id,
                        ObjectType.POSTER_SECTION,
                        key,
                        [{"kind": SourceRefKind.IMAGE_OCR_BLOCK.value, "ref": key}],
                    )
                    objects.append(
                        PosterSectionObject(
                            type=ObjectType.POSTER_SECTION,
                            object_id=object_id,
                            canvas_id=canvas.canvas_id,
                            bbox=section_bbox,
                            representation=Representation.NATIVE_OBJECT,
                            source_refs=[
                                SourceRef(
                                    kind=SourceRefKind.IMAGE_OCR_BLOCK,
                                    ref=f"{canvas.canvas_id}/{key}",
                                    occurrence_index=section_index,
                                )
                            ],
                            detector_evidence=[
                                DetectorEvidence(
                                    detector="image_poster_partition",
                                    label="spatial_section",
                                    details={"section_index": section_index},
                                )
                            ],
                            translatable_blocks=section_blocks,
                            execution_status=ExecutionStatus.PENDING,
                            planned_action="translate_overlay",
                            semantic_id=key,
                            semantic_scope="main",
                            semantic_occurrence_index=section_index,
                            section_role=f"section_{section_index}",
                        )
                    )
                    reading_order.append(object_id)

            image_key = f"image:{canvas.canvas_id}"
            image_id = build_object_id(
                prepared.source_sha256,
                canvas.canvas_id,
                ObjectType.IMAGE,
                image_key,
                [{"kind": SourceRefKind.IMAGE_OCR_BLOCK.value, "ref": canvas.canvas_id}],
            )
            objects.append(
                ImageObject(
                    type=ObjectType.IMAGE,
                    object_id=image_id,
                    canvas_id=canvas.canvas_id,
                    bbox=canvas_bbox,
                    representation=Representation.BITMAP,
                    source_refs=[
                        SourceRef(
                            kind=SourceRefKind.IMAGE_OCR_BLOCK,
                            ref=canvas.canvas_id,
                            occurrence_index=canvas.source_index,
                        )
                    ],
                    detector_evidence=[
                        DetectorEvidence(
                            detector="image_ocr",
                            label="text_block",
                            details={
                                "block_count": len(blocks),
                                "tile_count": len(tiles),
                            },
                        )
                    ],
                    translatable_blocks=blocks,
                    execution_status=ExecutionStatus.PENDING,
                    planned_action="ocr_overlay"
                    if len(tiles) == 1
                    else "ocr_overlay_tiled",
                    semantic_id=image_key,
                    semantic_scope="main",
                    occurrence_key=image_key,
                )
            )
            reading_order.append(image_id)
            canvas.reading_order = reading_order

        fig_hint = sum(
            1
            for box_list in frame_boxes.values()
            for item in box_list
            if "figure" in item[4].lower()
        )
        tab_hint = sum(
            1
            for box_list in frame_boxes.values()
            for item in box_list
            if "table" in item[4].lower()
        )
        auto_profile = (
            ContentProfile.POSTER
            if any(canvas.kind is CanvasKind.POSTER for canvas in prepared.canvases)
            else ContentProfile.GENERIC
        )
        decision = resolve_profile(
            auto_suggestion=auto_profile,
            confidence=0.9 if auto_profile is ContentProfile.POSTER else 0.6,
            evidence=[
                f"poster_canvas:{sum(1 for c in prepared.canvases if c.kind is CanvasKind.POSTER)}",
                f"ocr_blocks:{sum(len(b) for b in frame_boxes.values())}",
                f"figure_hint:{fig_hint}",
                f"table_hint:{tab_hint}",
            ],
            user_override=content_profile,
        )

        document = DocumentInfo(
            source_sha256=prepared.source_sha256,
            source_name=prepared.source_name,
            source_format=prepared.source_format,
            detected_mime=prepared.detected_mime,
            content_profile=decision.selected_profile,
            profile_source=decision.source,
            profile_confidence=decision.confidence,
            profile_evidence=decision.evidence,
            auto_profile_suggestion=decision.auto_suggestion,
            requested_mode=ProcessingMode.NATIVE,
            selected_mode=ProcessingMode.NATIVE,
            output_editability=OutputEditability.RASTERIZED,
            input_asset=prepared.input_asset,
            derived_assets=list(prepared.derived_assets),
            conversion_lineage=list(prepared.conversion_lineage),
        )

        manifest = DocumentStructureManifest(
            schema_version=CURRENT_SCHEMA_VERSION,
            manifest_id=build_manifest_id(prepared.source_sha256),
            created_at=datetime.now(timezone.utc),
            producer=ProducerInfo(name="qyunslation-plan-030f", version="1.0.0"),
            document=document,
            canvases=list(prepared.canvases),
            objects=objects,
            issues=issues,
            extensions={
                "translatable_block_count": sum(
                    len(item.translatable_blocks)
                    for item in objects
                    if item.translatable_blocks
                ),
                "frame_count": len(prepared.canvases),
                "tile_plan_required": any(
                    len(plan_image_tiles(int(c.width), int(c.height))) > 1
                    for c in prepared.canvases
                ),
            },
        )
        return manifest.refresh_summary()
