# SPDX-License-Identifier: MPL-2.0
"""PLAN-030c：PDF 题注驱动语义扫描。"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .captions import caption_anchors
from .ingest import prepare_document
from .layout import (
    TextBlock,
    body_blocks,
    column_of,
    overflows_column,
    reading_order,
)
from .representation import (
    document_representation,
    needs_ocr,
    page_representation,
)
from .references import classify_body, heading_y_from_blocks
from .tables import table_regions
from .models import (
    AssetRole,
    BodyObject,
    BoundingBox,
    CaptionObject,
    ContentProfile,
    DetectorEvidence,
    DocumentInfo,
    DocumentStructureManifest,
    ExecutionStatus,
    FigureObject,
    ImageObject,
    IssueSeverity,
    ManifestIssue,
    ObjectType,
    OutputEditability,
    PipelineStage,
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
    CURRENT_SCHEMA_VERSION,
    TranslatableBlock,
)
from .profiles import resolve_profile


PDF_STRUCTURE_SCANNER_NAME = "qyunslation-plan-030c"
PDF_STRUCTURE_SCANNER_VERSION = "1.5.0"


@dataclass(frozen=True, slots=True)
class _PageAnalysis:
    anchors: list
    table_regions_by_number: dict
    labeled_figures: dict[int, object]
    unnumbered_regions: list
    body_blocks: list[TextBlock]
    reference_heading_y: float | None


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


def _clip_text(page, bb) -> str:
    import pymupdf

    try:
        return (page.get_text("text", clip=pymupdf.Rect(bb)) or "").strip()
    except Exception:
        return ""


class PdfStructureScanner:
    """Produce a validated Manifest v1 from a PDF path."""

    def _unnumbered_images(
        self, regions: list, canvas, prepared, page_no: int
    ) -> list:
        """无题注页的可译区域：不伪造 Figure 编号，产出 IMAGE 对象。

        口径与 scan_pdf_tier3、pdf_image_translate 共用 translatable_regions
        （PLAN-027 不变量 4）；幻灯页由该函数走 PLAN-029b profile。
        """
        out: list = []
        for index, rect in enumerate(regions, start=1):
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

    @staticmethod
    def _table_region_evidence(regions_by_number, number, canvas, page_no):
        """表格区域几何。仅供保护与审计——030d 不做单元格重建。"""
        region = regions_by_number.get(number)
        if region is None:
            return []
        bbox = _clip_bbox(_rect_from_bbox(region.as_tuple()), canvas)
        return [
            DetectorEvidence(
                detector="table_rule_lines",
                label=f"table:{number}",
                confidence=0.8,
                bbox=bbox,
                details={
                    "page": page_no,
                    "rule_lines": region.line_count,
                    "reconstructed": False,
                },
            )
        ]

    def _body_objects(
        self,
        page,
        canvas,
        prepared,
        page_no: int,
        blocks: list[TextBlock],
        *,
        in_references: bool = False,
        heading_y: float | None = None,
    ) -> tuple[list, list]:
        """正文块建模为 BODY 对象，带页内阅读顺序。

        030d 只审计正文、不接管译文生成：正文仍由 BabelDOC 文字层翻译，因此对象
        终态为 EXPLICITLY_SKIPPED/delegated_to_babeldoc。033d：参考文献条目标
        skip，标题仍走文字层。
        """
        if not blocks:
            return [], []
        mode = canvas.layout_mode
        ordered = reading_order(page, mode, blocks)
        objects: list = []
        issues: list[ManifestIssue] = []
        for order, block in enumerate(ordered):
            key = f"body:page:{page_no}:{order}"
            object_id = build_object_id(
                prepared.source_sha256,
                canvas.canvas_id,
                ObjectType.BODY,
                key,
                [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": key}],
            )
            rect = _rect_from_bbox((block.x0, block.y0, block.x1, block.y1))
            body_bbox = _clip_bbox(rect, canvas)
            kind = classify_body(
                block.text,
                block.y0,
                in_references=in_references,
                heading_y=heading_y,
            )
            if kind == "entry":
                reason = "reference_entry"
                action = "skip"
                scope = "references"
            elif kind == "heading":
                reason = "delegated_to_babeldoc"
                action = "babeldoc_text_layer"
                scope = "references"
            else:
                reason = "delegated_to_babeldoc"
                action = "babeldoc_text_layer"
                scope = "body"
            objects.append(
                BodyObject(
                    type=ObjectType.BODY,
                    object_id=object_id,
                    canvas_id=canvas.canvas_id,
                    bbox=body_bbox,
                    representation=Representation.NATIVE_TEXT,
                    source_refs=[SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=key)],
                    detector_evidence=[
                        DetectorEvidence(
                            detector="pymupdf_text_blocks",
                            label=kind,
                            confidence=0.7,
                            bbox=body_bbox,
                            details={
                                "page": page_no,
                                "layout_mode": mode.value,
                                "column": column_of(block, page, mode),
                            },
                        )
                    ],
                    translatable_blocks=[
                        TranslatableBlock(
                            block_id=f"block:{order}",
                            source_text=block.text,
                            bbox=body_bbox,
                        )
                    ],
                    execution_status=ExecutionStatus.EXPLICITLY_SKIPPED,
                    reason_code=reason,
                    planned_action=action,
                    semantic_id=key,
                    semantic_scope=scope,
                    reading_order=order,
                )
            )
            if overflows_column(block, page, mode):
                issues.append(
                    ManifestIssue(
                        code="LAYOUT_COLUMN_OVERFLOW",
                        severity=IssueSeverity.WARNING,
                        stage=PipelineStage.SCAN,
                        object_id=object_id,
                        retryable=False,
                        message=(
                            f"page {page_no} narrow body block crosses the column midline"
                        ),
                        details={"page": page_no},
                    )
                )
        return objects, issues

    @staticmethod
    def _analyze_page(page) -> _PageAnalysis:
        from pdf_figure_crop import (
            labeled_figure_regions,
            page_caption_profile,
            translatable_regions,
        )

        import pymupdf

        anchors = caption_anchors(page)
        profile = page_caption_profile(page, anchors=anchors)
        try:
            drawings = page.get_drawings() or []
        except Exception:
            drawings = []
        try:
            raw_blocks = page.get_text("blocks") or []
        except Exception:
            raw_blocks = []
        detected_tables = table_regions(
            page, anchors=anchors, drawings=drawings
        )
        regions_by_number = {region.number: region for region in detected_tables}
        table_rectangles = [
            pymupdf.Rect(region.as_tuple()) for region in detected_tables
        ]
        labeled = labeled_figure_regions(
            page,
            profile=profile,
            tables=table_rectangles,
            drawings=drawings,
            text_blocks=raw_blocks,
        )
        unnumbered = []
        if not labeled:
            unnumbered = translatable_regions(
                page,
                profile=profile,
                tables=table_rectangles,
                drawings=drawings,
                text_blocks=raw_blocks,
            )
        exclusions = [*table_rectangles, *labeled.values(), *unnumbered]
        blocks = body_blocks(page, exclude_rects=exclusions, raw_blocks=raw_blocks)
        return _PageAnalysis(
            anchors=anchors,
            table_regions_by_number=regions_by_number,
            labeled_figures=labeled,
            unnumbered_regions=unnumbered,
            body_blocks=blocks,
            reference_heading_y=heading_y_from_blocks(raw_blocks),
        )

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
        import pymupdf

        canvases = {c.source_index: c for c in prepared.canvases}
        page_modes: dict[int, Representation] = {}
        objects: list = []
        issues: list[ManifestIssue] = []
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
            in_references = False
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
                page_modes[i] = page_representation(page)
                try:
                    analysis = self._analyze_page(page)
                except Exception as exc:
                    # 单页失败不得丢掉整份结构，但必须留痕而非静默
                    issues.append(
                        ManifestIssue(
                            code="SCAN_PAGE_FAILED",
                            severity=IssueSeverity.WARNING,
                            stage=PipelineStage.SCAN,
                            retryable=True,
                            message=f"page {i} scan failed: {exc}",
                            details={"page": i},
                        )
                    )
                    continue
                anchors = analysis.anchors
                labeled = analysis.labeled_figures
                regions_by_number = analysis.table_regions_by_number
                if analysis.unnumbered_regions:
                    objects.extend(
                        self._unnumbered_images(
                            analysis.unnumbered_regions, canvas, prepared, i
                        )
                    )
                if analysis.reference_heading_y is not None:
                    in_references = True
                body, body_issues = self._body_objects(
                    page,
                    canvas,
                    prepared,
                    i,
                    analysis.body_blocks,
                    in_references=in_references,
                    heading_y=analysis.reference_heading_y,
                )
                objects.extend(body)
                issues.extend(body_issues)
                canvas.reading_order = [b.object_id for b in body]
                missing_tables = [
                    num
                    for kind, num, *_ in anchors
                    if kind == "table" and num not in regions_by_number
                ]
                if missing_tables:
                    # 有表题注却测不到表格几何：表内文字会漏进正文，必须留痕
                    issues.append(
                        ManifestIssue(
                            code="TABLE_GEOMETRY_MISSING",
                            severity=IssueSeverity.WARNING,
                            stage=PipelineStage.SCAN,
                            retryable=False,
                            message=(
                                f"page {i} has table caption(s) {missing_tables} "
                                "but no table region could be delimited"
                            ),
                            details={"page": i, "tables": missing_tables},
                        )
                    )
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
                        cap_text = _clip_text(page, bb)
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
                                translatable_blocks=[
                                    TranslatableBlock(
                                        block_id=f"block:caption:{num}",
                                        source_text=cap_text,
                                        bbox=cap_bbox,
                                    )
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
                                translatable_blocks=[
                                    TranslatableBlock(
                                        block_id=f"block:figure:{num}",
                                        source_text=cap_text,
                                        bbox=body_bbox,
                                    )
                                ]
                                if region is not None
                                else [],
                            )
                        )
                    else:
                        if num in table_seen:
                            continue
                        table_seen.add(num)
                        tab_key = f"table:{num}"
                        tab_cap_text = _clip_text(page, bb)
                        region = regions_by_number.get(num)
                        tab_bbox = (
                            _clip_bbox(_rect_from_bbox(region.as_tuple()), canvas)
                            if region is not None
                            else cap_bbox
                        )
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
                                translatable_blocks=[
                                    TranslatableBlock(
                                        block_id=f"block:caption:table:{num}",
                                        source_text=tab_cap_text,
                                        bbox=cap_bbox,
                                    )
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
                                bbox=tab_bbox,
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
                                    ),
                                    *self._table_region_evidence(
                                        regions_by_number, num, canvas, i
                                    ),
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
        ordered_modes = [page_modes[k] for k in sorted(page_modes)]
        doc_representation = document_representation(ordered_modes)
        # 扫描页要经 HPD OCR 才能拿到文字层，落到 manifest 上就是 HYBRID
        selected_mode = (
            ProcessingMode.HYBRID
            if doc_representation is not Representation.NATIVE_TEXT
            else mode
        )
        if needs_ocr(ordered_modes):
            issues.append(
                ManifestIssue(
                    code="PAGES_REQUIRE_OCR",
                    severity=IssueSeverity.INFO,
                    stage=PipelineStage.SCAN,
                    retryable=False,
                    message=(
                        f"{sum(1 for m in ordered_modes if m is Representation.SCANNED)}"
                        " page(s) have no text layer and need HPD OCR"
                    ),
                    details={
                        "pages": [
                            k
                            for k in sorted(page_modes)
                            if page_modes[k] is Representation.SCANNED
                        ]
                    },
                )
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
            selected_mode=selected_mode,
            output_editability=OutputEditability.EDITABLE,
            input_asset=prepared.input_asset,
            derived_assets=list(prepared.derived_assets),
            conversion_lineage=list(prepared.conversion_lineage),
        )
        return DocumentStructureManifest(
            schema_version=CURRENT_SCHEMA_VERSION,
            manifest_id=build_manifest_id(prepared.source_sha256),
            created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
            producer=ProducerInfo(
                name=PDF_STRUCTURE_SCANNER_NAME,
                version=PDF_STRUCTURE_SCANNER_VERSION,
            ),
            document=document,
            canvases=list(prepared.canvases),
            objects=objects,
            issues=issues,
            extensions={
                "translatable_figure_count": sum(
                    1
                    for item in objects
                    if isinstance(item, (FigureObject, ImageObject))
                    and item.execution_status is ExecutionStatus.PENDING
                ),
                "truncated": truncated,
                "pages_scanned": pages_scanned,
                "document_representation": doc_representation.value,
                "page_representations": {
                    str(k): page_modes[k].value for k in sorted(page_modes)
                },
                "needs_ocr": needs_ocr(ordered_modes),
            },
        )
