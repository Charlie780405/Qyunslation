# SPDX-License-Identifier: MPL-2.0
"""PLAN-030c：PDF 题注驱动语义扫描。"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .captions import caption_anchors, continued_table_anchors
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
from .references import classify_body, heading_y_from_blocks, is_section_break
from .table_structure import (
    last_structure_meta,
    table_blocks_for_manifest,
    table_grid_dimensions,
)
from .tables import captionless_table_regions, table_regions
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
    TranslationPolicy,
    build_manifest_id,
    build_object_id,
    CURRENT_SCHEMA_VERSION,
    TranslatableBlock,
)
from .profiles import resolve_profile


PDF_STRUCTURE_SCANNER_NAME = "qyunslation-plan-030c"
PDF_STRUCTURE_SCANNER_VERSION = "1.8.0"


_REGULATORY_TEXT_SIGNALS = (
    ("clinical_trial", ("clinical trial", "临床试验")),
    ("registration", ("registration form", "registration number", "登记号")),
    ("eligibility", ("eligibility criteria", "inclusion criteria", "入选标准", "入组标准")),
    ("exclusion", ("exclusion criteria", "排除标准")),
    ("protocol", ("protocol number", "方案编号")),
    ("endpoint", ("primary endpoint", "secondary endpoint", "终点指标")),
    ("investigator", ("investigator", "研究者信息")),
    ("trial_status", ("trial status", "试验状态")),
    ("study_drug", ("investigational product", "试验药")),
)


@dataclass(frozen=True, slots=True)
class _PageAnalysis:
    anchors: list
    table_regions_by_number: dict
    captionless_tables: list
    labeled_figures: dict[int, object]
    unnumbered_regions: list
    body_blocks: list[TextBlock]
    reference_heading_y: float | None
    regulatory_signals: tuple[str, ...]


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


def _regulatory_signals(raw_blocks: list) -> tuple[str, ...]:
    text = "\n".join(
        str(block[4]) for block in raw_blocks if len(block) >= 5 and block[4]
    ).casefold()
    return tuple(
        name
        for name, variants in _REGULATORY_TEXT_SIGNALS
        if any(variant.casefold() in text for variant in variants)
    )


def _overlaps_existing_table(candidate, existing) -> bool:
    x0 = max(float(candidate.x0), float(existing.x0))
    y0 = max(float(candidate.y0), float(existing.y0))
    x1 = min(float(candidate.x1), float(existing.x1))
    y1 = min(float(candidate.y1), float(existing.y1))
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    candidate_area = max(1.0, (candidate.x1 - candidate.x0) * (candidate.y1 - candidate.y0))
    return intersection / candidate_area >= 0.8


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
    ) -> tuple[list, list, bool]:
        """正文块建模为 BODY 对象，带页内阅读顺序。

        030d 只审计正文、不接管译文生成：正文仍由 BabelDOC 文字层翻译，因此对象
        终态为 EXPLICITLY_SKIPPED/delegated_to_babeldoc。033h：参考文献标题与
        条目都 PRESERVE，BabelDOC 送 LLM 前必须消费该策略。
        返回 (objects, issues, still_in_references)。
        """
        if not blocks:
            return [], [], in_references
        mode = canvas.layout_mode
        ordered = reading_order(page, mode, blocks)
        objects: list = []
        issues: list[ManifestIssue] = []
        refs_active = in_references
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
            if is_section_break(block.text):
                refs_active = False
            kind = classify_body(
                block.text,
                block.y0,
                in_references=refs_active,
                heading_y=heading_y,
            )
            if kind == "heading":
                refs_active = True
            if kind in {"entry", "heading"}:
                reason = "reference_preserve" if kind == "heading" else "reference_entry"
                action = "preserve"
                scope = "references"
                policy = TranslationPolicy.PRESERVE
                block_role = "reference"
            else:
                reason = "delegated_to_babeldoc"
                action = "babeldoc_text_layer"
                scope = "body"
                policy = TranslationPolicy.TRANSLATE
                block_role = "body"
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
                            role=block_role,
                            translation_policy=policy,
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
        return objects, issues, refs_active

    @staticmethod
    def _analyze_page(page, *, allow_captionless: bool = False) -> _PageAnalysis:
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
        page_regulatory_signals = _regulatory_signals(raw_blocks)
        detected_tables = table_regions(page, anchors=anchors, drawings=drawings)
        anonymous_tables = []
        if allow_captionless or len(page_regulatory_signals) >= 2:
            anonymous_tables = [
                region
                for region in captionless_table_regions(
                    page,
                    drawings=drawings,
                    text_blocks=raw_blocks,
                )
                if not any(
                    _overlaps_existing_table(region, detected)
                    for detected in detected_tables
                )
            ]
        regions_by_number = {region.number: region for region in detected_tables}
        table_rectangles = [
            pymupdf.Rect(region.as_tuple())
            for region in [*detected_tables, *anonymous_tables]
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
            captionless_tables=anonymous_tables,
            labeled_figures=labeled,
            unnumbered_regions=unnumbered,
            body_blocks=blocks,
            reference_heading_y=heading_y_from_blocks(raw_blocks),
            regulatory_signals=page_regulatory_signals,
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
        table_occurrence_count: dict[int, int] = {}
        table_max_row: dict[int, int] = {}
        captionless_table_count = 0
        regulatory_signals: set[str] = set()
        regulatory_form_detected = False
        # Keep physical image resources separate from semantic Figure objects.
        # ``get_image_info`` reports occurrences; xrefs (and an inline fallback
        # key) let the manifest deduplicate a reused resource without losing the
        # number of page placements.
        physical_image_keys: set[str] = set()
        physical_image_occurrence_count = 0

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
                # A scanned page is already represented by its page canvas; an
                # additional image-resource walk is both redundant and costly
                # on the common full-page-scan path.  Native/hybrid pages still
                # expose embedded image resources for physical-vs-semantic
                # counts.
                if page_modes[i] is Representation.SCANNED:
                    image_infos = []
                else:
                    try:
                        image_infos = page.get_image_info(xrefs=True) or []
                    except Exception:
                        image_infos = []
                physical_image_occurrence_count += len(image_infos)
                for image_index, info in enumerate(image_infos):
                    xref = int(info.get("xref") or 0)
                    if xref:
                        physical_image_keys.add(f"xref:{xref}")
                    else:
                        # Inline images have no stable xref. The page-local
                        # occurrence is still a truthful physical resource key.
                        physical_image_keys.add(f"inline:page:{i}:{image_index}")
                try:
                    analysis = self._analyze_page(
                        page,
                        allow_captionless=regulatory_form_detected,
                    )
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
                regulatory_signals.update(analysis.regulatory_signals)
                if analysis.captionless_tables and len(analysis.regulatory_signals) >= 2:
                    regulatory_form_detected = True
                for index, region in enumerate(analysis.captionless_tables, start=1):
                    captionless_table_count += 1
                    key = f"table:page:{i}:anonymous:{index}"
                    table_id = build_object_id(
                        prepared.source_sha256,
                        canvas.canvas_id,
                        ObjectType.TABLE,
                        key,
                        [{"kind": SourceRefKind.PDF_DRAWING.value, "ref": key}],
                    )
                    bbox = _clip_bbox(_rect_from_bbox(region.as_tuple()), canvas)
                    blocks = table_blocks_for_manifest(
                        page,
                        region,
                        number=captionless_table_count,
                    )
                    objects.append(
                        TableObject(
                            type=ObjectType.TABLE,
                            object_id=table_id,
                            canvas_id=canvas.canvas_id,
                            bbox=bbox,
                            representation=Representation.NATIVE_TEXT,
                            row_count=region.row_count,
                            column_count=region.column_count,
                            source_refs=[
                                SourceRef(kind=SourceRefKind.PDF_DRAWING, ref=key)
                            ],
                            detector_evidence=[
                                DetectorEvidence(
                                    detector=region.detector,
                                    label="captionless_table",
                                    confidence=0.9,
                                    bbox=bbox,
                                    details={
                                        "page": i,
                                        "index": index,
                                        "rule_lines": region.line_count,
                                        "row_count": region.row_count,
                                        "column_count": region.column_count,
                                        "captionless": True,
                                    },
                                )
                            ],
                            translatable_blocks=blocks,
                            execution_status=ExecutionStatus.PENDING,
                            planned_action="translate_cells",
                            semantic_id=key,
                            semantic_scope="page",
                            semantic_occurrence_index=index,
                        )
                    )
                if analysis.unnumbered_regions:
                    objects.extend(
                        self._unnumbered_images(
                            analysis.unnumbered_regions, canvas, prepared, i
                        )
                    )
                if analysis.reference_heading_y is not None:
                    in_references = True
                body, body_issues, in_references = self._body_objects(
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
                        row_count = column_count = None
                        if region is not None:
                            row_count, column_count = table_grid_dimensions(
                                page,
                                region,
                                caption_text=tab_cap_text,
                                number=num,
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
                                representation=(
                                    Representation.BITMAP
                                    if region is not None and region.line_count == 0
                                    else Representation.NATIVE_TEXT
                                ),
                                row_count=row_count,
                                column_count=column_count,
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=tab_key)
                                ],
                                translatable_blocks=(
                                    table_blocks_for_manifest(
                                        page,
                                        region,
                                        caption_text=tab_cap_text,
                                        number=num,
                                    )
                                    if region is not None
                                    else [
                                        TranslatableBlock(
                                            block_id=f"table:{num}:title",
                                            source_text=tab_cap_text,
                                            bbox=cap_bbox,
                                            role="table_title",
                                            translation_policy=TranslationPolicy.TRANSLATE,
                                        )
                                    ]
                                ),
                                detector_evidence=[
                                    DetectorEvidence(
                                        detector=(
                                            "picture_table"
                                            if region is not None and region.line_count == 0
                                            else "caption_anchors"
                                        ),
                                        label=f"table:{num}",
                                        bbox=cap_bbox,
                                        details={
                                            "page": i,
                                            "picture_table": bool(
                                                region is not None and region.line_count == 0
                                            ),
                                            **(
                                                {
                                                    k: v
                                                    for k, v in last_structure_meta().items()
                                                    if k
                                                    in {
                                                        "grid_source",
                                                        "qc_codes",
                                                        "mismatch_rate",
                                                        "n_cols",
                                                        "n_rows",
                                                    }
                                                }
                                                if region is not None
                                                else {}
                                            ),
                                        },
                                    ),
                                    *self._table_region_evidence(
                                        regions_by_number, num, canvas, i
                                    ),
                                ],
                                execution_status=ExecutionStatus.PENDING,
                                planned_action="translate_cells",
                                semantic_id=f"table:{num}",
                                semantic_scope="main",
                                caption_ids=[cap_id],
                                semantic_occurrence_index=1,
                            )
                        )
                        blocks = objects[-1].translatable_blocks or []
                        row_indexes = [
                            b.row_index for b in blocks if b.row_index is not None
                        ]
                        if row_indexes:
                            table_max_row[num] = max(
                                table_max_row.get(num, -1), max(row_indexes)
                            )
                        table_occurrence_count[num] = 1
                continued = continued_table_anchors(page)
                if continued:
                    try:
                        cont_drawings = page.get_drawings() or []
                    except Exception:
                        cont_drawings = []
                    cont_rows = [
                        ("table", num, y0, bb) for num, y0, bb in continued
                    ]
                    cont_regions = {
                        region.number: region
                        for region in table_regions(
                            page, anchors=cont_rows, drawings=cont_drawings
                        )
                    }
                    for num, _y0, bb in continued:
                        occurrence_index = table_occurrence_count.get(num, 1) + 1
                        table_occurrence_count[num] = occurrence_index
                        cap_bbox = _clip_bbox(_rect_from_bbox(bb), canvas)
                        cap_key = f"table:{num}:caption:continued:{i}"
                        cap_id = build_object_id(
                            prepared.source_sha256,
                            canvas.canvas_id,
                            ObjectType.CAPTION,
                            cap_key,
                            [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": cap_key}],
                        )
                        tab_cap_text = _clip_text(page, bb)
                        region = cont_regions.get(num)
                        tab_bbox = (
                            _clip_bbox(_rect_from_bbox(region.as_tuple()), canvas)
                            if region is not None
                            else cap_bbox
                        )
                        tab_key = f"table:{num}:occ{occurrence_index}"
                        tab_id = build_object_id(
                            prepared.source_sha256,
                            canvas.canvas_id,
                            ObjectType.TABLE,
                            tab_key,
                            [{"kind": SourceRefKind.PDF_TEXT_BLOCK.value, "ref": tab_key}],
                        )
                        base_row = table_max_row.get(num, -1) + 1
                        row_count = column_count = None
                        blocks: list[TranslatableBlock] = []
                        if region is not None:
                            row_count, column_count = table_grid_dimensions(
                                page,
                                region,
                                caption_text="",
                                number=num,
                                base_row_offset=base_row,
                            )
                            blocks = table_blocks_for_manifest(
                                page,
                                region,
                                caption_text="",
                                number=num,
                                base_row_offset=base_row,
                            )
                        else:
                            issues.append(
                                ManifestIssue(
                                    code="TABLE_CONTINUATION_UNLINKED",
                                    severity=IssueSeverity.WARNING,
                                    stage=PipelineStage.SCAN,
                                    retryable=False,
                                    message=(
                                        f"page {i} continued table {num} "
                                        "has caption but no table region"
                                    ),
                                    details={"page": i, "table": num},
                                )
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
                                        block_id=f"block:caption:table:{num}:occ{occurrence_index}",
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
                                row_count=row_count,
                                column_count=column_count,
                                source_refs=[
                                    SourceRef(kind=SourceRefKind.PDF_TEXT_BLOCK, ref=tab_key)
                                ],
                                detector_evidence=[
                                    DetectorEvidence(
                                        detector="continued_table_anchors",
                                        label=f"table:{num}:occ{occurrence_index}",
                                        bbox=cap_bbox,
                                        details={"page": i, "continued": True},
                                    ),
                                    *(
                                        self._table_region_evidence(
                                            cont_regions, num, canvas, i
                                        )
                                        if region is not None
                                        else []
                                    ),
                                ],
                                translatable_blocks=blocks,
                                execution_status=ExecutionStatus.PENDING,
                                planned_action="translate_cells",
                                semantic_id=f"table:{num}",
                                semantic_scope="main",
                                caption_ids=[cap_id],
                                semantic_occurrence_index=occurrence_index,
                            )
                        )
                        row_indexes = [
                            b.row_index for b in blocks if b.row_index is not None
                        ]
                        if row_indexes:
                            table_max_row[num] = max(
                                table_max_row.get(num, -1), max(row_indexes)
                            )
        finally:
            doc.close()

        fig_n = len(figure_seen)
        tab_n = len(table_seen)
        from .profiles import suggest_content_profile

        suggested, confidence, evidence = suggest_content_profile(
            figure_caption_count=fig_n,
            table_caption_count=tab_n,
            captionless_table_count=captionless_table_count,
            regulatory_signals=tuple(sorted(regulatory_signals)),
        )
        decision = resolve_profile(
            auto_suggestion=suggested,
            confidence=confidence,
            evidence=evidence,
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
                "physical_image_count": len(physical_image_keys),
                "physical_image_occurrence_count": physical_image_occurrence_count,
                "semantic_figure_count": fig_n,
                "table_count": tab_n,
                "occurrence_count": sum(
                    1 for item in objects if item.type in {ObjectType.FIGURE, ObjectType.TABLE}
                ),
            },
        )
