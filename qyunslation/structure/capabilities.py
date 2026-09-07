"""Product format requirements and runtime capability decision contracts."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import ConfigDict, Field, model_validator

from .models import (
    ContractModel,
    OutputEditability,
    ProcessingMode,
    SourceFormat,
)


class CapabilityEnum(str, Enum):
    """Stable string values used by capability probes and consumers."""


class RequirementLevel(CapabilityEnum):
    CORE = "CORE"
    NORMALIZE = "NORMALIZE"
    CONDITIONAL = "CONDITIONAL"
    UNSUPPORTED = "UNSUPPORTED"


class RuntimeState(CapabilityEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class RuntimeFeature(CapabilityEnum):
    PDF_ENGINE = "PDF_ENGINE"
    OOXML_ENGINE = "OOXML_ENGINE"
    OFFICE_CONVERTER = "OFFICE_CONVERTER"
    IMAGE_DECODER = "IMAGE_DECODER"
    TIFF_DECODER = "TIFF_DECODER"
    SVG_DECODER = "SVG_DECODER"
    ANIMATED_IMAGE_DECODER = "ANIMATED_IMAGE_DECODER"
    HEIF_DECODER = "HEIF_DECODER"
    AVIF_DECODER = "AVIF_DECODER"
    OCR_ENGINE = "OCR_ENGINE"
    FONT_PACK = "FONT_PACK"
    SLIDE_RENDERER = "SLIDE_RENDERER"


class ModeCapability(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ProcessingMode
    output_editability: OutputEditability
    output_formats: tuple[str, ...]
    required_features: tuple[RuntimeFeature, ...]


class FormatCapability(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_format: SourceFormat
    requirement_level: RequirementLevel
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    magic_families: tuple[str, ...]
    modes: tuple[ModeCapability, ...]
    normalizes_to: SourceFormat | None = None
    issue_code: str | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> FormatCapability:
        if self.requirement_level is RequirementLevel.NORMALIZE and not self.normalizes_to:
            raise ValueError("NORMALIZATION_TARGET_REQUIRED")
        if self.requirement_level is RequirementLevel.UNSUPPORTED:
            if self.modes or not self.issue_code:
                raise ValueError("UNSUPPORTED_CAPABILITY_INVALID")
        elif not self.modes:
            raise ValueError("FORMAT_MODE_REQUIRED")
        return self


class CapabilityDecision(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_format: SourceFormat
    requirement_level: RequirementLevel
    runtime_state: RuntimeState
    requested_mode: ProcessingMode | None = None
    selected_mode: ProcessingMode | None = None
    missing_features: list[RuntimeFeature] = Field(default_factory=list)
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> CapabilityDecision:
        if self.runtime_state in {RuntimeState.DEGRADED, RuntimeState.UNAVAILABLE}:
            if not self.reason_code:
                raise ValueError("CAPABILITY_REASON_REQUIRED")
        if self.runtime_state is RuntimeState.AVAILABLE and self.selected_mode is None:
            raise ValueError("CAPABILITY_MODE_REQUIRED")
        return self


def _mode(
    mode: ProcessingMode,
    editability: OutputEditability,
    outputs: tuple[str, ...],
    features: tuple[RuntimeFeature, ...],
) -> ModeCapability:
    return ModeCapability(
        mode=mode,
        output_editability=editability,
        output_formats=outputs,
        required_features=features,
    )


_PDF_NATIVE = _mode(
    ProcessingMode.NATIVE,
    OutputEditability.EDITABLE,
    ("PDF",),
    (RuntimeFeature.PDF_ENGINE, RuntimeFeature.FONT_PACK),
)
_PDF_HYBRID = _mode(
    ProcessingMode.HYBRID,
    OutputEditability.MIXED,
    ("PDF",),
    (
        RuntimeFeature.PDF_ENGINE,
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
        RuntimeFeature.FONT_PACK,
    ),
)
_RENDERED_IMAGE = _mode(
    ProcessingMode.RENDERED,
    OutputEditability.RASTERIZED,
    ("IMAGE",),
    (
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
        RuntimeFeature.FONT_PACK,
    ),
)
_DOCX_NATIVE = _mode(
    ProcessingMode.NATIVE,
    OutputEditability.EDITABLE,
    ("DOCX",),
    (RuntimeFeature.OOXML_ENGINE, RuntimeFeature.FONT_PACK),
)
_DOCX_HYBRID = _mode(
    ProcessingMode.HYBRID,
    OutputEditability.MIXED,
    ("DOCX",),
    (
        RuntimeFeature.OOXML_ENGINE,
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
        RuntimeFeature.FONT_PACK,
    ),
)
_PPTX_NATIVE = _mode(
    ProcessingMode.NATIVE,
    OutputEditability.EDITABLE,
    ("PPTX",),
    (RuntimeFeature.OOXML_ENGINE, RuntimeFeature.FONT_PACK),
)
_PPTX_RENDERED = _mode(
    ProcessingMode.RENDERED,
    OutputEditability.RASTERIZED,
    ("PPTX", "PDF", "IMAGE_SET"),
    (
        RuntimeFeature.OOXML_ENGINE,
        RuntimeFeature.SLIDE_RENDERER,
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
        RuntimeFeature.FONT_PACK,
    ),
)
_PPTX_HYBRID = _mode(
    ProcessingMode.HYBRID,
    OutputEditability.MIXED,
    ("PPTX", "PDF"),
    (
        RuntimeFeature.OOXML_ENGINE,
        RuntimeFeature.SLIDE_RENDERER,
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
        RuntimeFeature.FONT_PACK,
    ),
)


def _image_capability(
    source_format: SourceFormat,
    extensions: tuple[str, ...],
    mime_types: tuple[str, ...],
    magic_family: str,
    *,
    level: RequirementLevel = RequirementLevel.CORE,
    extra_features: tuple[RuntimeFeature, ...] = (),
) -> FormatCapability:
    rendered = _RENDERED_IMAGE.model_copy(
        update={
            "output_formats": (source_format.value, "PNG"),
            "required_features": _RENDERED_IMAGE.required_features + extra_features,
        }
    )
    return FormatCapability(
        source_format=source_format,
        requirement_level=level,
        extensions=extensions,
        mime_types=mime_types,
        magic_families=(magic_family,),
        modes=(rendered,),
    )


_CAPABILITIES = (
    FormatCapability(
        source_format=SourceFormat.PDF,
        requirement_level=RequirementLevel.CORE,
        extensions=(".pdf",),
        mime_types=("application/pdf",),
        magic_families=("pdf",),
        modes=(_PDF_NATIVE, _PDF_HYBRID),
    ),
    FormatCapability(
        source_format=SourceFormat.DOCX,
        requirement_level=RequirementLevel.CORE,
        extensions=(".docx",),
        mime_types=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        magic_families=("ooxml-word",),
        modes=(_DOCX_NATIVE, _DOCX_HYBRID),
    ),
    FormatCapability(
        source_format=SourceFormat.DOC,
        requirement_level=RequirementLevel.NORMALIZE,
        extensions=(".doc",),
        mime_types=("application/msword",),
        magic_families=("ole-word",),
        modes=(
            _DOCX_NATIVE.model_copy(
                update={
                    "required_features": (
                        RuntimeFeature.OFFICE_CONVERTER,
                        RuntimeFeature.OOXML_ENGINE,
                        RuntimeFeature.FONT_PACK,
                    )
                }
            ),
        ),
        normalizes_to=SourceFormat.DOCX,
    ),
    _image_capability(SourceFormat.PNG, (".png",), ("image/png",), "png"),
    _image_capability(
        SourceFormat.JPEG,
        (".jpg", ".jpeg"),
        ("image/jpeg",),
        "jpeg",
    ),
    _image_capability(SourceFormat.WEBP, (".webp",), ("image/webp",), "webp"),
    _image_capability(SourceFormat.BMP, (".bmp",), ("image/bmp",), "bmp"),
    _image_capability(
        SourceFormat.TIFF,
        (".tif", ".tiff"),
        ("image/tiff",),
        "tiff",
        extra_features=(RuntimeFeature.TIFF_DECODER,),
    ),
    FormatCapability(
        source_format=SourceFormat.PPTX,
        requirement_level=RequirementLevel.CORE,
        extensions=(".pptx",),
        mime_types=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        magic_families=("ooxml-presentation",),
        modes=(_PPTX_NATIVE, _PPTX_HYBRID, _PPTX_RENDERED),
    ),
    FormatCapability(
        source_format=SourceFormat.PPT,
        requirement_level=RequirementLevel.NORMALIZE,
        extensions=(".ppt",),
        mime_types=("application/vnd.ms-powerpoint",),
        magic_families=("ole-presentation",),
        modes=(
            _PPTX_NATIVE.model_copy(
                update={
                    "required_features": (
                        RuntimeFeature.OFFICE_CONVERTER,
                        RuntimeFeature.OOXML_ENGINE,
                        RuntimeFeature.FONT_PACK,
                    )
                }
            ),
            _PPTX_RENDERED.model_copy(
                update={
                    "required_features": (
                        RuntimeFeature.OFFICE_CONVERTER,
                        RuntimeFeature.SLIDE_RENDERER,
                        RuntimeFeature.IMAGE_DECODER,
                        RuntimeFeature.OCR_ENGINE,
                        RuntimeFeature.FONT_PACK,
                    )
                }
            ),
        ),
        normalizes_to=SourceFormat.PPTX,
    ),
    _image_capability(
        SourceFormat.SVG,
        (".svg",),
        ("image/svg+xml",),
        "svg",
        level=RequirementLevel.CONDITIONAL,
        extra_features=(RuntimeFeature.SVG_DECODER,),
    ),
    _image_capability(
        SourceFormat.GIF,
        (".gif",),
        ("image/gif",),
        "gif",
        level=RequirementLevel.CONDITIONAL,
        extra_features=(RuntimeFeature.ANIMATED_IMAGE_DECODER,),
    ),
    _image_capability(
        SourceFormat.HEIF,
        (".heif",),
        ("image/heif",),
        "heif",
        level=RequirementLevel.CONDITIONAL,
        extra_features=(RuntimeFeature.HEIF_DECODER,),
    ),
    _image_capability(
        SourceFormat.HEIC,
        (".heic",),
        ("image/heic",),
        "heic",
        level=RequirementLevel.CONDITIONAL,
        extra_features=(RuntimeFeature.HEIF_DECODER,),
    ),
    _image_capability(
        SourceFormat.AVIF,
        (".avif",),
        ("image/avif",),
        "avif",
        level=RequirementLevel.CONDITIONAL,
        extra_features=(RuntimeFeature.AVIF_DECODER,),
    ),
    FormatCapability(
        source_format=SourceFormat.UNKNOWN,
        requirement_level=RequirementLevel.UNSUPPORTED,
        extensions=(),
        mime_types=("application/octet-stream",),
        magic_families=("unknown",),
        modes=(),
        issue_code="UNSUPPORTED_FORMAT",
    ),
)

_BY_FORMAT = {item.source_format: item for item in _CAPABILITIES}
_BY_EXTENSION = {
    extension: item.source_format
    for item in _CAPABILITIES
    for extension in item.extensions
}
_BY_MIME: dict[str, tuple[SourceFormat, ...]] = {}
for _capability in _CAPABILITIES:
    for _mime in _capability.mime_types:
        _BY_MIME[_mime] = (*_BY_MIME.get(_mime, ()), _capability.source_format)

if set(_BY_FORMAT) != set(SourceFormat) or len(_BY_FORMAT) != len(_CAPABILITIES):
    raise RuntimeError("format capability registry must cover each SourceFormat once")
if sum(len(item.extensions) for item in _CAPABILITIES) != len(_BY_EXTENSION):
    raise RuntimeError("format capability extensions must have exactly one owner")


def all_format_capabilities() -> tuple[FormatCapability, ...]:
    """Return the immutable product capability registry."""

    return _CAPABILITIES


def capability_for(source_format: SourceFormat) -> FormatCapability:
    """Return the policy for a known format, including UNKNOWN."""

    return _BY_FORMAT[source_format]


def source_format_for_extension(filename: str | Path) -> SourceFormat:
    """Map only a suffix; content verification belongs to the 030b probe."""

    extension = Path(str(filename)).suffix.lower()
    return _BY_EXTENSION.get(extension, SourceFormat.UNKNOWN)


def source_formats_for_mime(mime_type: str) -> tuple[SourceFormat, ...]:
    """Return all declared formats for a MIME type without guessing."""

    return _BY_MIME.get(mime_type.strip().lower(), (SourceFormat.UNKNOWN,))
