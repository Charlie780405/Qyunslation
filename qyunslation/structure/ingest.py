"""Fail-closed detection and preparation primitives for uploaded documents."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

from pydantic import ConfigDict, Field

from .capabilities import (
    RequirementLevel,
    capability_for,
    source_format_for_extension,
    source_formats_for_mime,
)
from .models import ContractModel, SourceFormat


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

