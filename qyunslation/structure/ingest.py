"""Fail-closed detection and preparation primitives for uploaded documents."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field

from .capabilities import (
    CapabilityDecision,
    RequirementLevel,
    RuntimeState,
    capability_for,
    source_format_for_extension,
    source_formats_for_mime,
)
from .models import (
    AssetRef,
    AssetRole,
    Canvas,
    ConversionStep,
    ContractModel,
    ProcessingMode,
    SourceFormat,
)

if TYPE_CHECKING:
    from .canvases import CanvasLimits
    from .runtime import RuntimeCapabilitySnapshot


DEFAULT_MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200.0

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


class InputPreparationError(ValueError):
    """Stable, user-safe input error raised before a task is created."""

    def __init__(self, code: str, message: str, *, http_status: int = 422):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"{code}: {message}")


class DetectedInput(ContractModel):
    """Detection evidence without retaining or serializing uploaded bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_name: str = Field(min_length=1)
    normalized_name: str = Field(min_length=1)
    source_format: SourceFormat
    extension_format: SourceFormat
    magic_format: SourceFormat
    declared_mime: str | None = None
    detected_mime: str = Field(min_length=1)
    magic_family: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """Validated bytes plus immutable provenance for downstream workflows."""

    source_name: str
    normalized_name: str
    source_format: SourceFormat
    normalized_format: SourceFormat
    detected_mime: str
    normalized_mime: str
    source_sha256: str
    normalized_sha256: str
    content: bytes = field(repr=False)
    input_asset: AssetRef
    derived_assets: tuple[AssetRef, ...]
    conversion_lineage: tuple[ConversionStep, ...]
    canvases: tuple[Canvas, ...]
    capability: CapabilityDecision
    workflow_type: str

    def audit_dict(self) -> dict[str, Any]:
        """Return metadata safe for task state and logs; never include payload bytes."""

        return {
            "source_name": self.source_name,
            "normalized_name": self.normalized_name,
            "source_format": self.source_format.value,
            "normalized_format": self.normalized_format.value,
            "detected_mime": self.detected_mime,
            "normalized_mime": self.normalized_mime,
            "source_sha256": self.source_sha256,
            "normalized_sha256": self.normalized_sha256,
            "workflow_type": self.workflow_type,
            "canvas_count": len(self.canvases),
            "capability": self.capability.model_dump(mode="json"),
            "input_asset": self.input_asset.model_dump(mode="json"),
            "derived_assets": [
                asset.model_dump(mode="json") for asset in self.derived_assets
            ],
            "conversion_lineage": [
                step.model_dump(mode="json") for step in self.conversion_lineage
            ],
        }


def sanitize_upload_name(filename: str | None) -> str:
    """Return a display-only basename with path and control characters removed."""

    raw = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _CONTROL_CHARS.sub("", raw).strip().strip(".")
    if not cleaned:
        return "uploaded_file"
    if len(cleaned) <= 240:
        return cleaned
    suffix = Path(cleaned).suffix[:20]
    stem_limit = max(1, 240 - len(suffix))
    return f"{Path(cleaned).stem[:stem_limit]}{suffix}"


def _archive_format(content: bytes) -> SourceFormat:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise InputPreparationError(
                    "ARCHIVE_LIMIT_EXCEEDED",
                    "Office 容器条目数量超过安全上限",
                    http_status=413,
                )

            total = 0
            for info in infos:
                total += info.file_size
                if (
                    info.file_size > MAX_ARCHIVE_MEMBER_BYTES
                    or total > MAX_ARCHIVE_TOTAL_BYTES
                ):
                    raise InputPreparationError(
                        "ARCHIVE_LIMIT_EXCEEDED",
                        "Office 容器解压尺寸超过安全上限",
                        http_status=413,
                    )
                if info.file_size and (
                    info.compress_size == 0
                    or info.file_size / info.compress_size
                    > MAX_ARCHIVE_COMPRESSION_RATIO
                ):
                    raise InputPreparationError(
                        "ARCHIVE_LIMIT_EXCEEDED",
                        "Office 容器压缩比超过安全上限",
                        http_status=413,
                    )

            names = {info.filename.replace("\\", "/") for info in infos}
    except InputPreparationError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InputPreparationError(
            "INVALID_CONTAINER", "ZIP/OOXML 容器损坏或不可读取"
        ) from exc

    if "[Content_Types].xml" not in names:
        return SourceFormat.UNKNOWN
    if "word/document.xml" in names:
        return SourceFormat.DOCX
    if "ppt/presentation.xml" in names:
        return SourceFormat.PPTX
    return SourceFormat.UNKNOWN


def _ole_format(content: bytes, extension_format: SourceFormat) -> SourceFormat:
    if extension_format in {SourceFormat.DOC, SourceFormat.PPT}:
        return extension_format
    try:
        import olefile

        with olefile.OleFileIO(io.BytesIO(content)) as ole:
            streams = {"/".join(parts) for parts in ole.listdir()}
    except Exception:
        return SourceFormat.UNKNOWN
    if "WordDocument" in streams:
        return SourceFormat.DOC
    if "PowerPoint Document" in streams:
        return SourceFormat.PPT
    return SourceFormat.UNKNOWN


def _isobmff_format(content: bytes) -> SourceFormat:
    if len(content) < 12 or content[4:8] != b"ftyp":
        return SourceFormat.UNKNOWN
    brands = {content[8:12]}
    brands.update(
        content[index : index + 4]
        for index in range(16, min(len(content), 64), 4)
        if len(content[index : index + 4]) == 4
    )
    if brands & {b"avif", b"avis"}:
        return SourceFormat.AVIF
    if brands & {b"heic", b"heix", b"hevc", b"hevx"}:
        return SourceFormat.HEIC
    if brands & {b"heif", b"heim", b"heis", b"mif1", b"msf1"}:
        return SourceFormat.HEIF
    return SourceFormat.UNKNOWN


def _detect_magic(
    content: bytes, extension_format: SourceFormat
) -> tuple[SourceFormat, str]:
    if content.startswith(b"%PDF-"):
        return SourceFormat.PDF, "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return SourceFormat.PNG, "png"
    if content.startswith(b"\xff\xd8\xff"):
        return SourceFormat.JPEG, "jpeg"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return SourceFormat.WEBP, "webp"
    if content.startswith(b"BM"):
        return SourceFormat.BMP, "bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return SourceFormat.TIFF, "tiff"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return SourceFormat.GIF, "gif"
    if content.startswith(_OLE_SIGNATURE):
        detected = _ole_format(content, extension_format)
        return detected, "ole" if detected is SourceFormat.UNKNOWN else capability_for(detected).magic_families[0]
    if content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        detected = _archive_format(content)
        family = (
            capability_for(detected).magic_families[0]
            if detected is not SourceFormat.UNKNOWN
            else "zip"
        )
        return detected, family

    bmff = _isobmff_format(content)
    if bmff is not SourceFormat.UNKNOWN:
        return bmff, capability_for(bmff).magic_families[0]

    prefix = content[:8192].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    if b"<svg" in prefix:
        return SourceFormat.SVG, "svg"
    return SourceFormat.UNKNOWN, "unknown"


def _canonical_mime(source_format: SourceFormat) -> str:
    capability = capability_for(source_format)
    return capability.mime_types[0]


def _normalized_name(source_name: str, source_format: SourceFormat) -> str:
    capability = capability_for(source_format)
    canonical_extension = capability.extensions[0]
    if source_format_for_extension(source_name) is source_format:
        return source_name
    stem = Path(source_name).stem if Path(source_name).suffix else source_name
    return f"{stem or 'uploaded_file'}{canonical_extension}"


def detect_input(
    filename: str | None,
    content: bytes,
    *,
    declared_mime: str | None = None,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> DetectedInput:
    """Detect a PLAN-030 format and reject contradictory or unsafe evidence."""

    if not content:
        raise InputPreparationError("EMPTY_FILE", "上传文件为空")
    if len(content) > max_bytes:
        raise InputPreparationError(
            "UPLOAD_TOO_LARGE",
            f"上传文件超过 {max_bytes} 字节限制",
            http_status=413,
        )

    source_name = sanitize_upload_name(filename)
    extension_format = source_format_for_extension(source_name)
    magic_format, magic_family = _detect_magic(content, extension_format)

    if magic_format is SourceFormat.UNKNOWN:
        if extension_format is not SourceFormat.UNKNOWN:
            code = (
                "INVALID_CONTAINER"
                if content.startswith((b"PK", _OLE_SIGNATURE))
                else "FORMAT_CONTENT_INVALID"
            )
            raise InputPreparationError(code, "文件内容与声明格式不构成有效文档")
        raise InputPreparationError(
            "UNSUPPORTED_FORMAT", "无法识别或不支持该文件格式", http_status=415
        )

    if (
        extension_format is not SourceFormat.UNKNOWN
        and extension_format is not magic_format
    ):
        raise InputPreparationError(
            "FORMAT_MISMATCH",
            f"文件扩展名表示 {extension_format.value}，内容实际为 {magic_format.value}",
            http_status=415,
        )

    normalized_declared_mime = (
        declared_mime.split(";", 1)[0].strip().lower() if declared_mime else None
    )
    if normalized_declared_mime not in _GENERIC_MIME_TYPES:
        mime_formats = source_formats_for_mime(normalized_declared_mime or "")
        if (
            mime_formats != (SourceFormat.UNKNOWN,)
            and magic_format not in mime_formats
        ):
            raise InputPreparationError(
                "MIME_MISMATCH",
                f"声明 MIME {normalized_declared_mime} 与内容格式 {magic_format.value} 不一致",
                http_status=415,
            )

    requirement = capability_for(magic_format).requirement_level
    if requirement is RequirementLevel.UNSUPPORTED:
        raise InputPreparationError(
            "UNSUPPORTED_FORMAT", "不支持该文件格式", http_status=415
        )

    return DetectedInput(
        source_name=source_name,
        normalized_name=_normalized_name(source_name, magic_format),
        source_format=magic_format,
        extension_format=extension_format,
        magic_format=magic_format,
        declared_mime=normalized_declared_mime,
        detected_mime=_canonical_mime(magic_format),
        magic_family=magic_family,
        source_sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


_IMAGE_FORMATS = {
    SourceFormat.PNG,
    SourceFormat.JPEG,
    SourceFormat.WEBP,
    SourceFormat.BMP,
    SourceFormat.TIFF,
    SourceFormat.SVG,
    SourceFormat.GIF,
    SourceFormat.HEIF,
    SourceFormat.HEIC,
    SourceFormat.AVIF,
}


def workflow_for_source_format(source_format: SourceFormat) -> str:
    """Map only normalized formats to an existing translation workflow."""

    if source_format is SourceFormat.PDF:
        return "markdown_based"
    if source_format is SourceFormat.DOCX:
        return "docx"
    if source_format is SourceFormat.PPTX:
        return "pptx"
    if source_format in _IMAGE_FORMATS:
        return "image_overlay"
    raise InputPreparationError(
        "WORKFLOW_ROUTE_UNSUPPORTED",
        f"{source_format.value} 尚无可执行翻译工作流",
        http_status=415,
    )


def _asset_id(role: AssetRole, sha256: str) -> str:
    return f"asset:{role.value.lower()}:{sha256}"


def prepare_document(
    filename: str | None,
    content: bytes,
    *,
    declared_mime: str | None = None,
    requested_mode: ProcessingMode | None = None,
    runtime_snapshot: RuntimeCapabilitySnapshot | None = None,
    office_converter: Any | None = None,
    canvas_limits: CanvasLimits | None = None,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> PreparedDocument:
    """Validate, normalize and describe one supported upload before task creation."""

    # Local imports avoid the deliberate adapter -> ingest error dependency cycle.
    from qyunslation.converter.office import LibreOfficeConverter

    from .canvases import extract_canvases
    from .runtime import decide_runtime_capability

    detected = detect_input(
        filename,
        content,
        declared_mime=declared_mime,
        max_bytes=max_bytes,
    )
    capability = decide_runtime_capability(
        detected.source_format,
        requested_mode=requested_mode,
        snapshot=runtime_snapshot,
    )
    if capability.runtime_state is RuntimeState.UNAVAILABLE:
        missing = ", ".join(feature.value for feature in capability.missing_features)
        detail = f"（缺少：{missing}）" if missing else ""
        raise InputPreparationError(
            "RUNTIME_CAPABILITY_UNAVAILABLE",
            f"当前运行环境不能处理 {detected.source_format.value}{detail}",
            http_status=503,
        )

    input_asset = AssetRef(
        asset_id=_asset_id(AssetRole.INPUT, detected.source_sha256),
        role=AssetRole.INPUT,
        sha256=detected.source_sha256,
        media_type=detected.detected_mime,
        locator=f"upload://{detected.source_name}",
    )
    normalized_name = detected.normalized_name
    normalized_format = detected.source_format
    normalized_content = content
    normalized_mime = detected.detected_mime
    derived_assets: tuple[AssetRef, ...] = ()
    conversion_lineage: tuple[ConversionStep, ...] = ()

    if detected.source_format in {SourceFormat.DOC, SourceFormat.PPT}:
        converter = office_converter or LibreOfficeConverter()
        conversion = converter.convert(
            detected.source_name,
            content,
            detected.source_format,
        )
        normalized = detect_input(
            conversion.output_name,
            conversion.content,
            max_bytes=max_bytes,
        )
        expected_format = capability_for(detected.source_format).normalizes_to
        if normalized.source_format is not expected_format:
            raise InputPreparationError(
                "OFFICE_OUTPUT_INVALID",
                "Office 规范化结果与产品格式契约不一致",
            )
        normalized_name = normalized.normalized_name
        normalized_format = normalized.source_format
        normalized_content = conversion.content
        normalized_mime = normalized.detected_mime
        normalized_asset = AssetRef(
            asset_id=_asset_id(AssetRole.NORMALIZED, normalized.source_sha256),
            role=AssetRole.NORMALIZED,
            sha256=normalized.source_sha256,
            media_type=normalized.detected_mime,
            locator=f"normalized://{normalized.normalized_name}",
        )
        derived_assets = (normalized_asset,)
        conversion_lineage = (
            ConversionStep(
                step_id=(
                    "normalize:"
                    f"{detected.source_sha256[:16]}:{normalized.source_sha256[:16]}"
                ),
                source_asset_id=input_asset.asset_id,
                output_asset_id=normalized_asset.asset_id,
                converter=conversion.converter,
                converter_version=conversion.converter_version,
                parameters=dict(conversion.parameters),
            ),
        )

    normalized_sha256 = hashlib.sha256(normalized_content).hexdigest()
    canvases = tuple(
        extract_canvases(
            normalized_format,
            normalized_content,
            limits=canvas_limits,
        )
    )
    return PreparedDocument(
        source_name=detected.source_name,
        normalized_name=normalized_name,
        source_format=detected.source_format,
        normalized_format=normalized_format,
        detected_mime=detected.detected_mime,
        normalized_mime=normalized_mime,
        source_sha256=detected.source_sha256,
        normalized_sha256=normalized_sha256,
        content=normalized_content,
        input_asset=input_asset,
        derived_assets=derived_assets,
        conversion_lineage=conversion_lineage,
        canvases=canvases,
        capability=capability,
        workflow_type=workflow_for_source_format(normalized_format),
    )
