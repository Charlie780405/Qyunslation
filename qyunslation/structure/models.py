"""Versioned public models for cross-format document structure manifests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CURRENT_SCHEMA_VERSION = "1.2.0"
SUPPORTED_SCHEMA_MAJOR = 1
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_ID_RE = re.compile(r"^manifest:[0-9a-f]{64}$")
_OBJECT_ID_RE = re.compile(r"^obj:[0-9a-f]{64}$")


class ContractEnum(str, Enum):
    """String enum with stable wire values."""


class SourceFormat(ContractEnum):
    PDF = "PDF"
    DOCX = "DOCX"
    DOC = "DOC"
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WEBP"
    BMP = "BMP"
    TIFF = "TIFF"
    PPTX = "PPTX"
    PPT = "PPT"
    SVG = "SVG"
    GIF = "GIF"
    HEIF = "HEIF"
    HEIC = "HEIC"
    AVIF = "AVIF"
    UNKNOWN = "UNKNOWN"


class ContentProfile(ContractEnum):
    RESEARCH_ARTICLE = "RESEARCH_ARTICLE"
    REVIEW_ARTICLE = "REVIEW_ARTICLE"
    PRESENTATION = "PRESENTATION"
    POSTER = "POSTER"
    REGULATORY = "REGULATORY"
    LETTER = "LETTER"
    GENERIC = "GENERIC"


class ProfileSource(ContractEnum):
    AUTO = "AUTO"
    USER_OVERRIDE = "USER_OVERRIDE"


class ProcessingMode(ContractEnum):
    NATIVE = "NATIVE"
    RENDERED = "RENDERED"
    HYBRID = "HYBRID"


class OutputEditability(ContractEnum):
    EDITABLE = "EDITABLE"
    MIXED = "MIXED"
    RASTERIZED = "RASTERIZED"


class CanvasKind(ContractEnum):
    PAGE = "PAGE"
    SECTION = "SECTION"
    SLIDE = "SLIDE"
    POSTER = "POSTER"


class CoordinateUnit(ContractEnum):
    PT = "PT"
    PX = "PX"
    EMU = "EMU"


class LayoutMode(ContractEnum):
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    MULTI = "MULTI"
    MIXED = "MIXED"
    FREEFORM = "FREEFORM"


class ObjectType(ContractEnum):
    BODY = "BODY"
    CAPTION = "CAPTION"
    FIGURE = "FIGURE"
    TABLE = "TABLE"
    TEXT_BOX = "TEXT_BOX"
    SHAPE = "SHAPE"
    IMAGE = "IMAGE"
    POSTER_SECTION = "POSTER_SECTION"


class Representation(ContractEnum):
    BITMAP = "BITMAP"
    VECTOR = "VECTOR"
    HYBRID = "HYBRID"
    NATIVE_TEXT = "NATIVE_TEXT"
    NATIVE_OBJECT = "NATIVE_OBJECT"
    SCANNED = "SCANNED"


class ExecutionStatus(ContractEnum):
    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    EXPLICITLY_SKIPPED = "EXPLICITLY_SKIPPED"
    FAILED_SOFT = "FAILED_SOFT"
    FAILED_HARD = "FAILED_HARD"


class BlockRole(ContractEnum):
    HEADING = "heading"
    BODY = "body"
    CAPTION = "caption"
    TABLE_TITLE = "table_title"
    TABLE_HEADER = "table_header"
    TABLE_GROUP = "table_group"
    TABLE_CELL = "table_cell"
    TABLE_FOOTNOTE = "table_footnote"
    FIGURE_TITLE = "figure_title"
    FIGURE_LABEL = "figure_label"
    FIGURE_BODY = "figure_body"
    FIGURE_FOOTNOTE = "figure_footnote"
    REFERENCE = "reference"


class TranslationPolicy(ContractEnum):
    TRANSLATE = "TRANSLATE"
    PRESERVE = "PRESERVE"
    PROTECT_TOKENS = "PROTECT_TOKENS"


class IssueSeverity(ContractEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class PipelineStage(ContractEnum):
    INGEST = "INGEST"
    NORMALIZE = "NORMALIZE"
    SCAN = "SCAN"
    TRANSLATE = "TRANSLATE"
    RENDER = "RENDER"
    PACKAGE = "PACKAGE"
    VALIDATE = "VALIDATE"


class AssetRole(ContractEnum):
    INPUT = "INPUT"
    NORMALIZED = "NORMALIZED"
    RENDERED = "RENDERED"
    TRANSLATED = "TRANSLATED"
    OUTPUT = "OUTPUT"


class SourceRefKind(ContractEnum):
    PDF_XREF = "PDF_XREF"
    PDF_DRAWING = "PDF_DRAWING"
    PDF_TEXT_BLOCK = "PDF_TEXT_BLOCK"
    DOCX_PART = "DOCX_PART"
    DOCX_RELATIONSHIP = "DOCX_RELATIONSHIP"
    PPTX_SLIDE = "PPTX_SLIDE"
    PPTX_SHAPE = "PPTX_SHAPE"
    IMAGE_OCR_BLOCK = "IMAGE_OCR_BLOCK"
    GENERATED_ASSET = "GENERATED_ASSET"


class ContractModel(BaseModel):
    """Forward-compatible reader model for Manifest v1."""

    model_config = ConfigDict(extra="allow")


class ProducerInfo(ContractModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class BoundingBox(ContractModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def validate_box(self) -> BoundingBox:
        values = (self.x0, self.y0, self.x1, self.y1)
        if (
            not all(math.isfinite(value) for value in values)
            or self.x0 < 0
            or self.y0 < 0
            or self.x1 <= self.x0
            or self.y1 <= self.y0
        ):
            raise ValueError("MANIFEST_BBOX_INVALID: bbox must have positive finite area")
        return self


class SourceGeometry(ContractModel):
    unit: CoordinateUnit | str
    bbox: tuple[float, float, float, float] | None = None
    transform: tuple[float, ...] | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AssetRef(ContractModel):
    asset_id: str = Field(min_length=1)
    role: AssetRole
    sha256: str
    media_type: str = Field(min_length=1)
    locator: str = Field(min_length=1)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("MANIFEST_SHA256_INVALID: expected full lowercase SHA-256")
        return value


class ConversionStep(ContractModel):
    step_id: str = Field(min_length=1)
    source_asset_id: str = Field(min_length=1)
    output_asset_id: str = Field(min_length=1)
    converter: str = Field(min_length=1)
    converter_version: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class DocumentInfo(ContractModel):
    source_sha256: str
    fast_fingerprint: str | None = None
    source_name: str = Field(min_length=1)
    source_format: SourceFormat
    detected_mime: str = Field(min_length=1)
    content_profile: ContentProfile
    profile_source: ProfileSource
    profile_confidence: float | None = Field(default=None, ge=0, le=1)
    profile_evidence: list[str] = Field(default_factory=list)
    auto_profile_suggestion: ContentProfile | None = None
    requested_mode: ProcessingMode
    selected_mode: ProcessingMode
    output_editability: OutputEditability
    input_asset: AssetRef
    derived_assets: list[AssetRef] = Field(default_factory=list)
    conversion_lineage: list[ConversionStep] = Field(default_factory=list)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("MANIFEST_SHA256_INVALID: expected full lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_profile_provenance(self) -> DocumentInfo:
        if self.profile_source is ProfileSource.AUTO:
            if self.profile_confidence is None or not self.profile_evidence:
                raise ValueError(
                    "MANIFEST_PROFILE_EVIDENCE_REQUIRED: AUTO profile needs confidence and evidence"
                )
        elif self.auto_profile_suggestion is None:
            raise ValueError(
                "MANIFEST_PROFILE_SUGGESTION_REQUIRED: USER_OVERRIDE must retain the auto suggestion"
            )
        return self


class Canvas(ContractModel):
    canvas_id: str = Field(min_length=1)
    kind: CanvasKind
    source_index: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: CoordinateUnit
    rotation: Literal[0, 90, 180, 270] = 0
    layout_mode: LayoutMode
    reading_order: list[str] = Field(default_factory=list)
    source_geometry: SourceGeometry | None = None

    @field_validator("unit")
    @classmethod
    def validate_canonical_unit(cls, value: CoordinateUnit) -> CoordinateUnit:
        if value is CoordinateUnit.EMU:
            raise ValueError("MANIFEST_CANVAS_UNIT_INVALID: canonical unit must be PT or PX")
        return value


class SourceRef(ContractModel):
    kind: SourceRefKind
    ref: str = Field(min_length=1)
    occurrence_index: int | None = Field(default=None, ge=1)
    source_geometry: SourceGeometry | None = None


class DetectorEvidence(ContractModel):
    detector: str = Field(min_length=1)
    label: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    bbox: BoundingBox | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SourceStyle(ContractModel):
    font_name: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    italic: bool | None = None
    alignment: str | None = None
    rotation: float | None = None
    writing_direction: str | None = None


class TranslatableBlock(ContractModel):
    block_id: str = Field(min_length=1)
    source_text: str
    bbox: BoundingBox | None = None
    source_language: str | None = None
    role: BlockRole | str | None = None
    translation_policy: TranslationPolicy | str | None = None
    source_style: SourceStyle | None = None
    row_index: int | None = Field(default=None, ge=0)
    column_index: int | None = Field(default=None, ge=0)
    row_span: int | None = Field(default=None, ge=1)
    column_span: int | None = Field(default=None, ge=1)


class BlockExecutionEvidence(ContractModel):
    block_id: str | None = None
    detection: str | None = None
    queued: bool | None = None
    translated: bool | None = None
    laid_out: bool | None = None
    validated: bool | None = None
    qc: list[str] | dict[str, Any] | None = None
    final_font_size: float | None = None
    final_font_weight: str | None = None
    output_bbox: BoundingBox | None = None


class OutputEvidence(ContractModel):
    asset_ids: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    blocks: list[BlockExecutionEvidence] = Field(default_factory=list)


class SemanticObjectBase(ContractModel):
    type: ObjectType
    object_id: str
    canvas_id: str = Field(min_length=1)
    bbox: BoundingBox | None = None
    representation: Representation
    source_refs: list[SourceRef] = Field(default_factory=list)
    detector_evidence: list[DetectorEvidence] = Field(default_factory=list)
    translatable_blocks: list[TranslatableBlock] = Field(default_factory=list)
    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    reason_code: str | None = None
    planned_action: str | None = None
    output_evidence: OutputEvidence | None = None
    semantic_id: str | None = None
    semantic_scope: str | None = None
    semantic_occurrence_index: int = Field(default=1, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_geometry: SourceGeometry | None = None

    @field_validator("object_id")
    @classmethod
    def validate_object_id(cls, value: str) -> str:
        if not _OBJECT_ID_RE.fullmatch(value):
            raise ValueError("MANIFEST_OBJECT_ID_INVALID: expected obj:<sha256>")
        return value

    @model_validator(mode="after")
    def validate_terminal_reason(self) -> SemanticObjectBase:
        needs_reason = {
            ExecutionStatus.EXPLICITLY_SKIPPED,
            ExecutionStatus.FAILED_SOFT,
            ExecutionStatus.FAILED_HARD,
        }
        if self.execution_status in needs_reason and not self.reason_code:
            raise ValueError(
                "MANIFEST_REASON_REQUIRED: skipped and failed objects need a reason code"
            )
        return self


class BodyObject(SemanticObjectBase):
    type: Literal[ObjectType.BODY]
    reading_order: int | None = Field(default=None, ge=0)


class CaptionObject(SemanticObjectBase):
    type: Literal[ObjectType.CAPTION]
    caption_for: list[str] = Field(default_factory=list)


class FigureObject(SemanticObjectBase):
    type: Literal[ObjectType.FIGURE]
    caption_ids: list[str] = Field(default_factory=list)
    child_object_ids: list[str] = Field(default_factory=list)


class TableObject(SemanticObjectBase):
    type: Literal[ObjectType.TABLE]
    caption_ids: list[str] = Field(default_factory=list)
    row_count: int | None = Field(default=None, ge=0)
    column_count: int | None = Field(default=None, ge=0)


class TextBoxObject(SemanticObjectBase):
    type: Literal[ObjectType.TEXT_BOX]
    z_order: int | None = None


class ShapeObject(SemanticObjectBase):
    type: Literal[ObjectType.SHAPE]
    z_order: int | None = None


class ImageObject(SemanticObjectBase):
    type: Literal[ObjectType.IMAGE]
    occurrence_key: str | None = None


class PosterSectionObject(SemanticObjectBase):
    type: Literal[ObjectType.POSTER_SECTION]
    section_role: str | None = None


SemanticObject = Annotated[
    BodyObject
    | CaptionObject
    | FigureObject
    | TableObject
    | TextBoxObject
    | ShapeObject
    | ImageObject
    | PosterSectionObject,
    Field(discriminator="type"),
]


class ManifestIssue(ContractModel):
    code: str = Field(min_length=1)
    severity: IssueSeverity
    stage: PipelineStage
    object_id: str | None = None
    retryable: bool = False
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ManifestSummary(ContractModel):
    figure_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    object_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    issue_counts: dict[str, int] = Field(default_factory=dict)


def _schema_major(version: str) -> int:
    match = _SEMVER_RE.fullmatch(version)
    if not match or int(match.group(1)) != SUPPORTED_SCHEMA_MAJOR:
        raise ValueError(
            f"MANIFEST_VERSION_UNSUPPORTED: expected major {SUPPORTED_SCHEMA_MAJOR}, got {version!r}"
        )
    return int(match.group(1))


def _require_sha256(value: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError("expected full lowercase SHA-256")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_manifest_id(source_sha256: str, schema_version: str = CURRENT_SCHEMA_VERSION) -> str:
    """Build a stable manifest identity from the source and schema major."""

    source_sha256 = _require_sha256(source_sha256)
    major = _schema_major(schema_version)
    digest = hashlib.sha256(f"{major}:{source_sha256}".encode()).hexdigest()
    return f"manifest:{digest}"


def build_object_id(
    source_sha256: str,
    canvas_id: str,
    object_type: ObjectType | str,
    semantic_key: str,
    source_refs: list[dict[str, Any]],
) -> str:
    """Build an order-independent deterministic identity for a semantic object."""

    source_sha256 = _require_sha256(source_sha256)
    refs = sorted(_canonical_json(ref) for ref in source_refs)
    payload = {
        "source_sha256": source_sha256,
        "canvas_id": canvas_id,
        "object_type": str(
            object_type.value if isinstance(object_type, ObjectType) else object_type
        ),
        "semantic_key": semantic_key,
        "source_refs": refs,
    }
    return f"obj:{hashlib.sha256(_canonical_json(payload).encode()).hexdigest()}"


def _derive_summary(
    objects: list[SemanticObject], issues: list[ManifestIssue]
) -> ManifestSummary:
    object_counts = Counter(item.type.value for item in objects)
    status_counts = Counter(item.execution_status.value for item in objects)
    issue_counts = Counter(issue.severity.value for issue in issues)

    def semantic_count(object_type: ObjectType) -> int:
        matching = [item for item in objects if item.type is object_type]
        numbered = {
            (item.semantic_scope or "", item.semantic_id)
            for item in matching
            if item.semantic_id
        }
        unnumbered = sum(item.semantic_id is None for item in matching)
        return len(numbered) + unnumbered

    return ManifestSummary(
        figure_count=semantic_count(ObjectType.FIGURE),
        table_count=semantic_count(ObjectType.TABLE),
        object_counts=dict(sorted(object_counts.items())),
        status_counts=dict(sorted(status_counts.items())),
        issue_counts=dict(sorted(issue_counts.items())),
    )


class DocumentStructureManifest(ContractModel):
    schema_version: str = CURRENT_SCHEMA_VERSION
    manifest_id: str
    created_at: datetime
    producer: ProducerInfo
    document: DocumentInfo
    canvases: list[Canvas]
    objects: list[SemanticObject] = Field(default_factory=list)
    issues: list[ManifestIssue] = Field(default_factory=list)
    summary: ManifestSummary | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        _schema_major(value)
        return value

    @field_validator("manifest_id")
    @classmethod
    def validate_manifest_id_shape(cls, value: str) -> str:
        if not _MANIFEST_ID_RE.fullmatch(value):
            raise ValueError("MANIFEST_ID_INVALID: expected manifest:<sha256>")
        return value

    def refresh_summary(self) -> DocumentStructureManifest:
        """按当前对象与问题重算 summary。

        执行阶段回写 execution_status 后必须调用，否则 summary 与对象不一致，
        序列化后无法通过 MANIFEST_SUMMARY_MISMATCH 校验。
        """
        self.summary = _derive_summary(self.objects, self.issues)
        return self

    @model_validator(mode="after")
    def validate_manifest_invariants(self) -> DocumentStructureManifest:
        expected_manifest_id = build_manifest_id(
            self.document.source_sha256, self.schema_version
        )
        if self.manifest_id != expected_manifest_id:
            raise ValueError("MANIFEST_ID_MISMATCH: identity does not match source")
        if self.document.input_asset.sha256 != self.document.source_sha256:
            raise ValueError("MANIFEST_SOURCE_ASSET_MISMATCH: input hash differs")
        if self.document.input_asset.role is not AssetRole.INPUT:
            raise ValueError(
                "MANIFEST_INPUT_ASSET_ROLE_INVALID: input asset must use INPUT role"
            )

        assets = [self.document.input_asset, *self.document.derived_assets]
        asset_ids = [asset.asset_id for asset in assets]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("MANIFEST_ASSET_ID_DUPLICATE: asset IDs must be unique")
        if any(asset.role is AssetRole.INPUT for asset in self.document.derived_assets):
            raise ValueError(
                "MANIFEST_DERIVED_ASSET_ROLE_INVALID: derived assets cannot use INPUT role"
            )
        known_assets = set(asset_ids)
        lineage_step_ids = [
            step.step_id for step in self.document.conversion_lineage
        ]
        if len(set(lineage_step_ids)) != len(lineage_step_ids):
            raise ValueError(
                "MANIFEST_LINEAGE_STEP_ID_DUPLICATE: conversion step IDs must be unique"
            )
        for step in self.document.conversion_lineage:
            if (
                step.source_asset_id not in known_assets
                or step.output_asset_id not in known_assets
            ):
                raise ValueError(
                    "MANIFEST_LINEAGE_ASSET_UNKNOWN: conversion step references an unknown asset"
                )
            if step.source_asset_id == step.output_asset_id:
                raise ValueError(
                    "MANIFEST_LINEAGE_SELF_REFERENCE: conversion source and output must differ"
                )
        lineage_graph: dict[str, set[str]] = {}
        for step in self.document.conversion_lineage:
            lineage_graph.setdefault(step.source_asset_id, set()).add(
                step.output_asset_id
            )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit_asset(asset_id: str) -> None:
            if asset_id in visiting:
                raise ValueError(
                    "MANIFEST_LINEAGE_CYCLE: conversion lineage must be acyclic"
                )
            if asset_id in visited:
                return
            visiting.add(asset_id)
            for output_id in lineage_graph.get(asset_id, set()):
                visit_asset(output_id)
            visiting.remove(asset_id)
            visited.add(asset_id)

        for asset_id in known_assets:
            visit_asset(asset_id)

        canvases = {canvas.canvas_id: canvas for canvas in self.canvases}
        if len(canvases) != len(self.canvases):
            raise ValueError("MANIFEST_CANVAS_ID_DUPLICATE: canvas IDs must be unique")

        object_ids = [item.object_id for item in self.objects]
        if len(set(object_ids)) != len(object_ids):
            raise ValueError("MANIFEST_OBJECT_ID_DUPLICATE: object IDs must be unique")

        semantic_occurrences: set[tuple[str, str, str, int]] = set()
        for item in self.objects:
            canvas = canvases.get(item.canvas_id)
            if canvas is None:
                raise ValueError(
                    f"MANIFEST_CANVAS_UNKNOWN: object references {item.canvas_id!r}"
                )
            if item.bbox is not None:
                if canvas.kind is CanvasKind.SECTION:
                    raise ValueError(
                        "MANIFEST_BBOX_INVALID: flow-layout SECTION objects must not carry bbox"
                    )
                if item.bbox.x1 > canvas.width or item.bbox.y1 > canvas.height:
                    raise ValueError(
                        "MANIFEST_BBOX_INVALID: object bbox exceeds its canvas"
                    )
            elif canvas.kind is not CanvasKind.SECTION:
                raise ValueError(
                    "MANIFEST_BBOX_REQUIRED: page/slide/poster objects must carry bbox"
                )
            if item.type in {ObjectType.FIGURE, ObjectType.TABLE} and item.semantic_id:
                occurrence = (
                    item.type.value,
                    item.semantic_scope or "",
                    item.semantic_id,
                    item.semantic_occurrence_index,
                )
                if occurrence in semantic_occurrences:
                    raise ValueError(
                        "MANIFEST_SEMANTIC_ID_DUPLICATE: semantic occurrence must be unique within scope"
                    )
                semantic_occurrences.add(occurrence)

        known_objects = set(object_ids)
        objects_by_id = {item.object_id: item for item in self.objects}
        for canvas in self.canvases:
            if len(set(canvas.reading_order)) != len(canvas.reading_order):
                raise ValueError(
                    "MANIFEST_READING_ORDER_DUPLICATE: reading order cannot repeat objects"
                )
            for ordered_id in canvas.reading_order:
                ordered = objects_by_id.get(ordered_id)
                if ordered is None:
                    raise ValueError(
                        "MANIFEST_READING_ORDER_UNKNOWN: reading order references an unknown object"
                    )
                if ordered.canvas_id != canvas.canvas_id:
                    raise ValueError(
                        "MANIFEST_READING_ORDER_CANVAS_MISMATCH: object belongs to another canvas"
                    )

        for item in self.objects:
            relationship_ids: list[str] = []
            if isinstance(item, CaptionObject):
                relationship_ids.extend(item.caption_for)
            if isinstance(item, (FigureObject, TableObject)):
                relationship_ids.extend(item.caption_ids)
            if isinstance(item, FigureObject):
                relationship_ids.extend(item.child_object_ids)
            if any(related_id not in known_objects for related_id in relationship_ids):
                raise ValueError(
                    "MANIFEST_RELATION_OBJECT_UNKNOWN: object relationship is dangling"
                )
            if item.object_id in relationship_ids:
                raise ValueError(
                    "MANIFEST_RELATION_SELF_REFERENCE: object cannot reference itself"
                )
            if isinstance(item, (FigureObject, TableObject)) and any(
                objects_by_id[caption_id].type is not ObjectType.CAPTION
                for caption_id in item.caption_ids
            ):
                raise ValueError(
                    "MANIFEST_CAPTION_TYPE_INVALID: caption_ids must reference CAPTION objects"
                )
            if item.output_evidence and any(
                asset_id not in known_assets for asset_id in item.output_evidence.asset_ids
            ):
                raise ValueError(
                    "MANIFEST_OUTPUT_ASSET_UNKNOWN: output evidence references an unknown asset"
                )

        for issue in self.issues:
            if issue.object_id and issue.object_id not in known_objects:
                raise ValueError(
                    "MANIFEST_ISSUE_OBJECT_UNKNOWN: issue references an unknown object"
                )

        derived = _derive_summary(self.objects, self.issues)
        if self.summary is not None:
            for field_name in self.summary.model_fields_set:
                if getattr(self.summary, field_name) != getattr(derived, field_name):
                    raise ValueError(
                        f"MANIFEST_SUMMARY_MISMATCH: {field_name} is not derived from objects/issues"
                    )
        object.__setattr__(self, "summary", derived)

        if self.extensions.get("terminal") is True:
            pending = [
                item.object_id
                for item in self.objects
                if item.execution_status is ExecutionStatus.PENDING
            ]
            if pending:
                raise ValueError(
                    "MANIFEST_PENDING_IN_SUCCESS: terminal results cannot contain PENDING objects"
                )
        _reject_model_trace_secrets(self.extensions.get("model_trace"))
        return self


_SECRET_MARKERS = ("api_key", "authorization", "sk-", "token=", "password")


def _reject_model_trace_secrets(trace: Any) -> None:
    if not trace:
        return
    blob = _canonical_json(trace).lower()
    if any(marker in blob for marker in _SECRET_MARKERS):
        raise ValueError("MODEL_TRACE_SECRET: credentials must not be recorded")
