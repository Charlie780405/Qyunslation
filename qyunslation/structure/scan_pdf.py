# SPDX-License-Identifier: MPL-2.0
"""PLAN-030c：PDF 题注驱动语义扫描。"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .captions import caption_anchors
from .ingest import prepare_document
from .models import (
    AssetRole,
    BoundingBox,
    CaptionObject,
    ContentProfile,
    DetectorEvidence,
    DocumentInfo,
    DocumentStructureManifest,
    ExecutionStatus,
    FigureObject,
    ImageObject,
    ObjectType,
    OutputEditability,
    ProcessingMode,
    ProducerInfo,
    ProfileSource,
    Representation,
    SourceFormat,
    SourceGeometry,
    SourceRef,
    SourceRefKind,
    TableObject,
    build_manifest_id,
    build_object_id,
)
from .profiles import resolve_profile


def _clip_bbox(rect, canvas) -> BoundingBox:
    x0 = max(0.0, float(rect.x0))
    y0 = max(0.0, float(rect.y0))
    x1 = min(float(canvas.width), float(rect.x1))
    y1 = min(float(canvas.height), float(rect.y1))
    if x1 <= x0:
        x1 = min(float(canvas.width), x0 + 1.0)
    if y1 <= y0:
        y1 = min(float(canvas.height), y0 + 1.0)
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _rect_from_bbox(bb) -> object:
    class _R:
        def __init__(self, x0, y0, x1, y1):
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    return _R(float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))


class PdfStructureScanner:
    """Produce a validated Manifest v1 from a PDF path."""

    def _unnumbered_images(self, page, canvas, prepared, page_no: int) -> list:
        """无题注页的可译区域：不伪造 Figure 编号，产出 IMAGE 对象。

        口径与 scan_pdf_tier3、pdf_image_translate 共用 translatable_regions
        （PLAN-027 不变量 4）；幻灯页由该函数走 PLAN-029b profile。
        """
        from pdf_figure_crop import translatable_regions

        out: list = []
        for index, rect in enumerate(translatable_regions(page), start=1):
            key = f"image:page:{page_no}:{index}"
            object_id = build_object_id(
                prepared.source_sha256,
                canvas.canvas_id,
                ObjectType.IMAGE,
                key,
                [{"kind": SourceRefKind.PDF_DRAWING.value, "ref": key}],
            )
            out.append(
                ImageObject(
                    type=ObjectType.IMAGE,
                    object_id=object_id,
                    canvas_id=canvas.canvas_id,
                    bbox=_clip_bbox(rect, canvas),
                    representation=Representation.HYBRID,
                    source_refs=[SourceRef(kind=SourceRefKind.PDF_DRAWING, ref=key)],
                    detector_evidence=[
                        DetectorEvidence(
                            detector="translatable_regions",
                            label="unnumbered_region",
                            bbox=_clip_bbox(rect, canvas),
                            details={"page": page_no, "index": index},
                        )
                    ],
                    execution_status=ExecutionStatus.PENDING,
                    planned_action="ocr_overlay",
                    semantic_id=key,
                    semantic_scope="unnumbered",
                    occurrence_key=key,
                )
            )
        return out

    def scan(
        self,
        source: Path,
        *,
        content_profile: ContentProfile | None = None,
        processing_mode: ProcessingMode | None = None,
        max_pages: int | None = None,
        deadline_s: float | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> DocumentStructureManifest:
        """扫描 PDF 结构。

        max_pages / deadline_s / should_abort 供 Tier-3 预扫描控制预算；触发任一
        限制时 manifest 标 truncated，调用方不应缓存不完整结果。
        """
        path = Path(source)
        content = path.read_bytes()
        mode = processing_mode or ProcessingMode.NATIVE
        prepared = prepare_document(
            path.name,
            content,
            declared_mime="application/pdf",
            requested_mode=mode,
        )
        if prepared.normalized_format is not SourceFormat.PDF:
            raise ValueError("SCAN_FORMAT_UNSUPPORTED: PdfStructureScanner only accepts PDF")

        scripts = Path(__file__).resolve().parents[2] / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from pdf_figure_crop import labeled_figure_regions

        import pymupdf

        canvases = {c.source_index: c for c in prepared.canvases}
        objects: list = []
        figure_seen: set[int] = set()
        table_seen: set[int] = set()

        started = time.monotonic()
        pages_scanned = 0
        truncated = False

        doc = pymupdf.open(stream=prepared.content, filetype="pdf")
        try:
            total = len(doc)
            limit = total if max_pages is None else min(total, max(int(max_pages), 0))
            if limit < total:
                truncated = True
            for i, page in enumerate(doc, start=1):
                if i > limit:
                    break
                if should_abort is not None and should_abort():
                    truncated = True
                    break
                if deadline_s is not None and time.monotonic() - started > deadline_s:
                    truncated = True
                    break
                canvas = canvases.get(i)
                if canvas is None:
                    continue
                pages_scanned += 1
                anchors = caption_anchors(page)
                labeled = labeled_figure_regions(page)
                if not labeled:
                    objects.extend(self._unnumbered_images(page, canvas, prepared, i))
                for kind, num, y0, bb in anchors:
                    cap_bbox = _clip_bbox(_rect_from_bbox(bb), canvas)
                    cap_key = f"{kind}:{num}:caption:{i}"
                    cap_id = build_object_id(
                        prepared.source_sha256,
                        canvas.canvas_id,
                        ObjectType.CAPTION,
                        cap_key,
                        [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": cap_key}],
                    )
                    if kind == "figure":
                        if num in figure_seen:
                            continue
                        figure_seen.add(num)
                        region = labeled.get(num)
                        body_bbox = _clip_bbox(region, canvas) if region is not None else cap_bbox
                        fig_key = f"figure:{num}"
                        fig_id = build_object_id(
                            prepared.source_sha256,
                            canvas.canvas_id,
                            ObjectType.FIGURE,
                            fig_key,
                            [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": fig_key}],
                        )
                        skipped = region is None
                        objects.append(
                            CaptionObject(
                                type=ObjectType.CAPTION,
                                object_id=cap_id,
                                canvas_id=canvas.canvas_id,
                                bbox=cap_bbox,
                                representation=Representation.NATIVE_TEXT,
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=cap_key)
                                ],
                                caption_for=[fig_id],
                                semantic_id=f"caption:figure:{num}",
                                semantic_scope="main",
                            )
                        )
                        objects.append(
                            FigureObject(
                                type=ObjectType.FIGURE,
                                object_id=fig_id,
                                canvas_id=canvas.canvas_id,
                                bbox=body_bbox,
                                representation=(
                                    Representation.HYBRID if region is not None else Representation.NATIVE_TEXT
                                ),
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=fig_key)
                                ],
                                detector_evidence=[
                                    DetectorEvidence(
                                        detector="caption_anchors",
                                        label=f"figure:{num}",
                                        bbox=cap_bbox,
                                        details={"page": i, "has_region": region is not None},
                                    )
                                ],
                                execution_status=(
                                    ExecutionStatus.EXPLICITLY_SKIPPED
                                    if skipped
                                    else ExecutionStatus.PENDING
                                ),
                                reason_code="no_translatable_region" if skipped else None,
                                planned_action="skip" if skipped else "ocr_overlay",
                                semantic_id=f"figure:{num}",
                                semantic_scope="main",
                                caption_ids=[cap_id],
                            )
                        )
                    else:
                        if num in table_seen:
                            continue
                        table_seen.add(num)
                        tab_key = f"table:{num}"
                        tab_id = build_object_id(
                            prepared.source_sha256,
                            canvas.canvas_id,
                            ObjectType.TABLE,
                            tab_key,
                            [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": tab_key}],
                        )
                        objects.append(
                            CaptionObject(
                                type=ObjectType.CAPTION,
                                object_id=cap_id,
                                canvas_id=canvas.canvas_id,
                                bbox=cap_bbox,
                                representation=Representation.NATIVE_TEXT,
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=cap_key)
                                ],
                                caption_for=[tab_id],
                                semantic_id=f"caption:table:{num}",
                                semantic_scope="main",
                            )
                        )
                        objects.append(
                            TableObject(
                                type=ObjectType.TABLE,
                                object_id=tab_id,
                                canvas_id=canvas.canvas_id,
                                bbox=cap_bbox,
                                representation=Representation.NATIVE_TEXT,
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=tab_key)
                                ],
                                detector_evidence=[
                                    DetectorEvidence(
                                        detector="caption_anchors",
                                        label=f"table:{num}",
                                        bbox=cap_bbox,
                                        details={"page": i},
                                    )
                                ],
                                execution_status=ExecutionStatus.EXPLICITLY_SKIPPED,
                                reason_code="text_layer_table",
                                planned_action="text_layer",
                                semantic_id=f"table:{num}",
                                semantic_scope="main",
                                caption_ids=[cap_id],
                            )
                        )
        finally:
            doc.close()

        fig_n = len(figure_seen)
        tab_n = len(table_seen)
        decision = resolve_profile(
            auto_suggestion=ContentProfile.RESEARCH_ARTICLE,
            confidence=0.92 if fig_n or tab_n else 0.4,
            evidence=[
                f"figure_captions:{fig_n}",
                f"table_captions:{tab_n}",
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
            requested_mode=mode,
            selected_mode=mode,
            output_editability=OutputEditability.EDITABLE,
            input_asset=prepared.input_asset,
            derived_assets=list(prepared.derived_assets),
            conversion_lineage=list(prepared.conversion_lineage),
        )
        return DocumentStructureManifest(
            schema_version="1.0.0",
            manifest_id=build_manifest_id(prepared.source_sha256),
            created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            producer=ProducerInfo(name="qyunslation-plan-030c", version="1.0.0"),
            document=document,
            canvases=list(prepared.canvases),
            objects=objects,
            issues=[],
            extensions={
                "translatable_figure_count": sum(
                    1
                    for item in objects
                    if isinstance(item, (FigureObject, ImageObject))
                    and item.execution_status is ExecutionStatus.PENDING
                ),
                "truncated": truncated,
                "pages_scanned": pages_scanned,
            },
        )
