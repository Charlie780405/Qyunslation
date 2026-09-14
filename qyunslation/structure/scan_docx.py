# SPDX-License-Identifier: MPL-2.0
"""PLAN-030e：DOCX 结构扫描，产出 DocumentStructureManifest。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import docx
from collections import Counter

from qyunslation.extensions.docx_image_overlay import enumerate_drawing_occurrences
from qyunslation.structure.captions import (
    continued_table_caption_num,
    figure_caption_num,
    table_caption_num,
)
from qyunslation.structure.docx_walk import DocxWalkSegment, walk_docx
from qyunslation.structure.ingest import prepare_document
from qyunslation.structure.models import (
    AssetRole,
    BlockRole,
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
    SourceRef,
    SourceRefKind,
    TableObject,
    TextBoxObject,
    TranslationPolicy,
    TranslatableBlock,
    build_manifest_id,
    build_object_id,
    CURRENT_SCHEMA_VERSION,
)
from qyunslation.structure.profiles import resolve_profile
from qyunslation.structure.table_cell_policy import classify_cell_policy


class DocxStructureScanner:
    """Produce a validated Manifest v1 from a DOCX path or bytes."""

    def scan(
        self,
        source: Path | str | bytes,
        *,
        source_name: str = "document.docx",
        content_profile: ContentProfile | None = None,
    ) -> DocumentStructureManifest:
        if isinstance(source, (Path, str)):
            path = Path(source)
            content = path.read_bytes()
            source_name = path.name
        else:
            content = bytes(source)

        prepared = prepare_document(source_name, content)
        if prepared.source_format is not SourceFormat.DOCX:
            raise ValueError(f"DocxStructureScanner expects DOCX, got {prepared.source_format}")

        _, segments, elements, texts = walk_docx(content)
        doc = docx.Document(BytesIO(content))
        drawing_occ = enumerate_drawing_occurrences(doc)
        physical_image_keys = {
            (occ.container, occ.embed_rid) for occ in drawing_occ
        }

        objects: list = []
        issues: list[ManifestIssue] = []
        canvas_ids = {canvas.canvas_id for canvas in prepared.canvases}
        if not prepared.canvases:
            raise ValueError("DOCX scan requires at least one SECTION canvas")

        reading_by_canvas: dict[str, list[str]] = {
            canvas.canvas_id: [] for canvas in prepared.canvases
        }
        body_ids: list[str] = []
        caption_by_num: dict[tuple[str, int], str] = {}
        caption_ids_by_num: dict[tuple[str, int], list[str]] = {}
        caption_occurrence: Counter[tuple[str, int]] = Counter()
        table_cells: dict[int, list[tuple[int, int, int, DocxWalkSegment, str]]] = {}
        # PLAN-038g: pending caption consumed by the next physical table
        pending_table_caption: tuple[int, int, str] | None = None  # num, occ, cap_id
        table_caption_meta: dict[int, tuple[int, int, str]] = {}  # tbl_idx -> meta
        textbox_segments: list[tuple[int, DocxWalkSegment]] = []

        for segment in segments:
            canvas_id = self._resolve_canvas_id(segment, canvas_ids, issues)
            if canvas_id is None:
                continue

            fig_num = figure_caption_num(segment.text)
            cont_tab_num = continued_table_caption_num(segment.text)
            tab_num = cont_tab_num if cont_tab_num is not None else table_caption_num(segment.text)
            if fig_num is not None:
                cap_id = self._append_caption(
                    objects,
                    prepared,
                    canvas_id,
                    kind="figure",
                    number=fig_num,
                    segment=segment,
                    occurrence_index=caption_occurrence[("figure", fig_num)] + 1,
                )
                reading_by_canvas[canvas_id].append(cap_id)
                caption_occurrence[("figure", fig_num)] += 1
                caption_ids_by_num.setdefault(("figure", fig_num), []).append(cap_id)
                if ("figure", fig_num) not in caption_by_num:
                    caption_by_num[("figure", fig_num)] = cap_id
                continue
            if tab_num is not None:
                occ = caption_occurrence[("table", tab_num)] + 1
                cap_id = self._append_caption(
                    objects,
                    prepared,
                    canvas_id,
                    kind="table",
                    number=tab_num,
                    segment=segment,
                    occurrence_index=occ,
                )
                reading_by_canvas[canvas_id].append(cap_id)
                caption_occurrence[("table", tab_num)] = occ
                caption_ids_by_num.setdefault(("table", tab_num), []).append(cap_id)
                if ("table", tab_num) not in caption_by_num:
                    caption_by_num[("table", tab_num)] = cap_id
                pending_table_caption = (tab_num, occ, cap_id)
                continue

            if segment.is_textbox:
                textbox_segments.append((segment.section_index, segment))
                continue

            if segment.table_path is not None:
                tbl_idx, row_idx, col_idx = segment.table_path
                if pending_table_caption is not None and tbl_idx not in table_caption_meta:
                    table_caption_meta[tbl_idx] = pending_table_caption
                    pending_table_caption = None
                table_cells.setdefault(tbl_idx, []).append(
                    (row_idx, col_idx, tbl_idx, segment, canvas_id)
                )
                continue

            body_id = self._append_body(objects, prepared, canvas_id, segment)
            body_ids.append(body_id)
            reading_by_canvas[canvas_id].append(body_id)

        row_offset_by_num: dict[int, int] = {}
        for tbl_idx in sorted(table_cells):
            cells = table_cells[tbl_idx]
            canvas_id = cells[0][4]
            meta = table_caption_meta.get(tbl_idx)
            self._append_table(
                objects,
                prepared,
                canvas_id,
                tbl_idx,
                [(row, col, idx, segment) for row, col, idx, segment, _ in cells],
                caption_by_num,
                reading_by_canvas,
                caption_meta=meta,
                row_offset_by_num=row_offset_by_num,
            )

        for index, (section_index, segment) in enumerate(textbox_segments, start=1):
            canvas_id = self._resolve_canvas_id(
                segment,
                canvas_ids,
                issues,
                fallback_section=section_index,
            )
            if canvas_id is None:
                continue
            textbox_id = self._append_textbox(
                objects, prepared, canvas_id, index, segment
            )
            reading_by_canvas[canvas_id].append(textbox_id)

        default_canvas_id = prepared.canvases[0].canvas_id
        figure_nums = sorted(n for k, n in caption_by_num if k == "figure")
        image_object_ids: list[str] = []
        for index, occ in enumerate(drawing_occ, start=1):
            key = f"image:docx:{occ.container}:{occ.embed_rid}:{index}"
            rel_ref = f"{occ.container}/{occ.embed_rid}"
            object_id = build_object_id(
                prepared.source_sha256,
                default_canvas_id,
                ObjectType.FIGURE if index - 1 < len(figure_nums) else ObjectType.IMAGE,
                key,
                [{"kind": SourceRefKind.DOCX_RELATIONSHIP.value, "ref": rel_ref}],
            )
            planned = "ocr_overlay"
            fig_num = figure_nums[index - 1] if index - 1 < len(figure_nums) else None
            fig_caps = caption_ids_by_num.get(("figure", fig_num or 0), [])
            cap_id = fig_caps[index - 1] if index - 1 < len(fig_caps) else None
            fig_occurrence = index if fig_num is not None else 1
            if cap_id:
                obj_type = ObjectType.FIGURE
                sem_id = f"figure:{fig_num}"
                fig_cap_ids = [cap_id]
            else:
                obj_type = ObjectType.IMAGE
                sem_id = key
                fig_cap_ids = []
            if obj_type is ObjectType.FIGURE:
                objects.append(
                    FigureObject(
                        type=ObjectType.FIGURE,
                        object_id=object_id,
                        canvas_id=default_canvas_id,
                        bbox=None,
                        representation=Representation.BITMAP,
                        source_refs=[
                            SourceRef(
                                kind=SourceRefKind.DOCX_RELATIONSHIP,
                                ref=rel_ref,
                                occurrence_index=index,
                            )
                        ],
                        detector_evidence=[
                            DetectorEvidence(
                                detector="enumerate_drawing_occurrences",
                                label="drawing_blip",
                                details={
                                    "container": occ.container,
                                    "embed_rid": occ.embed_rid,
                                    "width_pt": occ.width_pt,
                                    "height_pt": occ.height_pt,
                                },
                            )
                        ],
                        execution_status=ExecutionStatus.PENDING,
                        planned_action=planned,
                        semantic_id=sem_id,
                        semantic_scope="main",
                        semantic_occurrence_index=fig_occurrence,
                        caption_ids=fig_cap_ids,
                    )
                )
            else:
                objects.append(
                    ImageObject(
                        type=ObjectType.IMAGE,
                        object_id=object_id,
                        canvas_id=default_canvas_id,
                        bbox=None,
                        representation=Representation.BITMAP,
                        source_refs=[
                            SourceRef(
                                kind=SourceRefKind.DOCX_RELATIONSHIP,
                                ref=rel_ref,
                                occurrence_index=index,
                            )
                        ],
                        detector_evidence=[
                            DetectorEvidence(
                                detector="enumerate_drawing_occurrences",
                                label="drawing_blip",
                                details={
                                    "container": occ.container,
                                    "embed_rid": occ.embed_rid,
                                },
                            )
                        ],
                        execution_status=ExecutionStatus.PENDING,
                        planned_action=planned,
                        semantic_id=sem_id,
                        semantic_scope="main",
                        occurrence_key=key,
                    )
                )
            image_object_ids.append(object_id)
            reading_by_canvas[default_canvas_id].append(object_id)
            if cap_id:
                self._link_caption(objects, cap_id, object_id)

        for canvas in prepared.canvases:
            canvas.reading_order = reading_by_canvas.get(canvas.canvas_id, [])

        fig_n = len(figure_nums)
        tab_n = len({k for k in caption_by_num if k[0] == "table"})
        from .profiles import suggest_content_profile

        suggested, confidence, evidence = suggest_content_profile(
            figure_caption_count=fig_n,
            table_caption_count=tab_n,
        )
        decision = resolve_profile(
            auto_suggestion=suggested,
            confidence=confidence,
            evidence=evidence,
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
            output_editability=OutputEditability.EDITABLE,
            input_asset=prepared.input_asset,
            derived_assets=list(prepared.derived_assets),
            conversion_lineage=list(prepared.conversion_lineage),
        )

        manifest = DocumentStructureManifest(
            schema_version=CURRENT_SCHEMA_VERSION,
            manifest_id=build_manifest_id(prepared.source_sha256),
            created_at=datetime.now(timezone.utc),
            producer=ProducerInfo(name="qyunslation-plan-030e", version="1.0.0"),
            document=document,
            canvases=list(prepared.canvases),
            objects=objects,
            issues=issues,
            extensions={
                "translatable_figure_count": sum(
                    1
                    for item in objects
                    if item.type in (ObjectType.FIGURE, ObjectType.IMAGE)
                    and item.execution_status is ExecutionStatus.PENDING
                ),
                "segment_count": len(segments),
                "drawing_occurrence_count": len(drawing_occ),
                "physical_image_count": len(physical_image_keys),
                "physical_image_occurrence_count": len(drawing_occ),
                "semantic_figure_count": fig_n,
                "table_count": tab_n,
                "occurrence_count": sum(
                    1 for item in objects if item.type in {ObjectType.FIGURE, ObjectType.TABLE}
                ),
            },
        )
        return manifest.refresh_summary()

    @staticmethod
    def _resolve_canvas_id(
        segment: DocxWalkSegment,
        canvas_ids: set[str],
        issues: list[ManifestIssue],
        *,
        fallback_section: int | None = None,
    ) -> str | None:
        section_index = fallback_section or segment.section_index
        canvas_id = f"section:{section_index}"
        if canvas_id in canvas_ids:
            return canvas_id
        issues.append(
            ManifestIssue(
                severity=IssueSeverity.WARNING,
                code="DOCX_SECTION_CANVAS_MISSING",
                message=f"No SECTION canvas for section {section_index}",
                details={
                    "container_ref": segment.container_ref,
                    "section_index": section_index,
                },
            )
        )
        return None

    def _source_ref(self, segment: DocxWalkSegment) -> SourceRef:
        return SourceRef(
            kind=SourceRefKind.DOCX_PART,
            ref=segment.container_ref,
            occurrence_index=segment.segment_index + 1,
        )

    def _block(self, segment: DocxWalkSegment) -> TranslatableBlock:
        return TranslatableBlock(
            block_id=f"block:{segment.segment_index}",
            source_text=segment.text,
            source_language=None,
        )

    def _append_body(
        self,
        objects: list,
        prepared,
        canvas_id: str,
        segment: DocxWalkSegment,
    ) -> str:
        key = f"body:{segment.container_ref}:{segment.segment_index}"
        refs = [{"kind": SourceRefKind.DOCX_PART.value, "ref": segment.container_ref}]
        object_id = build_object_id(
            prepared.source_sha256,
            canvas_id,
            ObjectType.BODY,
            key,
            refs,
        )
        objects.append(
            BodyObject(
                type=ObjectType.BODY,
                object_id=object_id,
                canvas_id=canvas_id,
                bbox=None,
                representation=Representation.NATIVE_TEXT,
                source_refs=[self._source_ref(segment)],
                detector_evidence=[
                    DetectorEvidence(
                        detector="docx_walk",
                        label="paragraph",
                        details={"container_ref": segment.container_ref},
                    )
                ],
                translatable_blocks=[self._block(segment)],
                execution_status=ExecutionStatus.PENDING,
                planned_action="translate_inline",
                semantic_id=key,
                semantic_scope="main",
                reading_order=segment.segment_index,
            )
        )
        return object_id

    def _append_caption(
        self,
        objects: list,
        prepared,
        canvas_id: str,
        *,
        kind: str,
        number: int,
        segment: DocxWalkSegment,
        occurrence_index: int = 1,
    ) -> str:
        key = f"caption:{kind}:{number}:{occurrence_index}"
        refs = [{"kind": SourceRefKind.DOCX_PART.value, "ref": segment.container_ref}]
        object_id = build_object_id(
            prepared.source_sha256,
            canvas_id,
            ObjectType.CAPTION,
            key,
            refs,
        )
        caption_for: list[str] = []
        objects.append(
            CaptionObject(
                type=ObjectType.CAPTION,
                object_id=object_id,
                canvas_id=canvas_id,
                bbox=None,
                representation=Representation.NATIVE_TEXT,
                source_refs=[self._source_ref(segment)],
                translatable_blocks=[self._block(segment)],
                execution_status=ExecutionStatus.PENDING,
                planned_action="translate_inline",
                semantic_id=f"caption:{kind}:{number}",
                semantic_scope="main",
                semantic_occurrence_index=occurrence_index,
                caption_for=caption_for,
            )
        )
        return object_id

    @staticmethod
    def _link_caption(objects: list, caption_id: str, target_id: str) -> None:
        for obj in objects:
            if obj.object_id == caption_id and isinstance(obj, CaptionObject):
                obj.caption_for = [target_id]
                return

    def _append_table(
        self,
        objects: list,
        prepared,
        canvas_id: str,
        tbl_idx: int,
        cells: list[tuple[int, int, int, DocxWalkSegment]],
        caption_by_num: dict[tuple[str, int], str],
        reading_by_canvas: dict[str, list[str]],
        *,
        caption_meta: tuple[int, int, str] | None = None,
        row_offset_by_num: dict[int, int] | None = None,
    ) -> None:
        rows = max(row for row, _, _, _ in cells) + 1
        cols = max(col for _, col, _, _ in cells) + 1
        if caption_meta is not None:
            tab_num, occurrence_index, cap_id = caption_meta
        else:
            tab_num = tbl_idx + 1
            occurrence_index = 1
            cap_id = caption_by_num.get(("table", tab_num))
        base_row = 0
        if row_offset_by_num is not None:
            base_row = int(row_offset_by_num.get(tab_num, 0))
        blocks: list[TranslatableBlock] = []
        for row_idx, col_idx, _, segment in sorted(cells):
            block = self._block(segment)
            block.block_id = f"cell:{tbl_idx}:{row_idx}:{col_idx}"
            block.role = BlockRole.TABLE_CELL
            block.translation_policy = classify_cell_policy(segment.text)
            block.row_index = base_row + row_idx
            block.column_index = col_idx
            blocks.append(block)

        key = f"table:{tab_num}:occ:{occurrence_index}"
        refs = [{"kind": SourceRefKind.DOCX_PART.value, "ref": f"table:{tbl_idx}"}]
        object_id = build_object_id(
            prepared.source_sha256,
            canvas_id,
            ObjectType.TABLE,
            key,
            refs,
        )
        caption_ids = [cap_id] if cap_id else []
        objects.append(
            TableObject(
                type=ObjectType.TABLE,
                object_id=object_id,
                canvas_id=canvas_id,
                bbox=None,
                representation=Representation.NATIVE_TEXT,
                source_refs=[
                    SourceRef(kind=SourceRefKind.DOCX_PART, ref=f"table:{tbl_idx}")
                ],
                translatable_blocks=blocks,
                execution_status=ExecutionStatus.PENDING,
                planned_action="translate_cells",
                semantic_id=f"table:{tab_num}",
                semantic_scope="main",
                semantic_occurrence_index=occurrence_index,
                row_count=rows,
                column_count=cols,
                caption_ids=caption_ids,
            )
        )
        if cap_id:
            self._link_caption(objects, cap_id, object_id)
        reading_by_canvas[canvas_id].append(object_id)
        if row_offset_by_num is not None:
            row_offset_by_num[tab_num] = base_row + rows

    def _append_textbox(
        self,
        objects: list,
        prepared,
        canvas_id: str,
        index: int,
        segment: DocxWalkSegment,
    ) -> str:
        key = f"textbox:{index}"
        refs = [{"kind": SourceRefKind.DOCX_PART.value, "ref": segment.container_ref}]
        object_id = build_object_id(
            prepared.source_sha256,
            canvas_id,
            ObjectType.TEXT_BOX,
            key,
            refs,
        )
        objects.append(
            TextBoxObject(
                type=ObjectType.TEXT_BOX,
                object_id=object_id,
                canvas_id=canvas_id,
                bbox=None,
                representation=Representation.NATIVE_TEXT,
                source_refs=[self._source_ref(segment)],
                translatable_blocks=[self._block(segment)],
                execution_status=ExecutionStatus.PENDING,
                planned_action="translate_inline",
                semantic_id=key,
                semantic_scope="main",
            )
        )
        return object_id
