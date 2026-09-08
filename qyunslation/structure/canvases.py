"""Canonical canvas extraction for supported PLAN-030 input containers."""

from __future__ import annotations

import io
import warnings
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from .capabilities import capability_for
from .ingest import InputPreparationError, detect_input
from .layout import detect_layout_mode
from .models import (
    Canvas,
    CanvasKind,
    CoordinateUnit,
    LayoutMode,
    SourceFormat,
    SourceGeometry,
)


@dataclass(frozen=True, slots=True)
class CanvasLimits:
    max_image_pixels: int = 200_000_000
    max_image_frames: int = 1_000
    max_document_canvases: int = 10_000

    def __post_init__(self) -> None:
        if min(
            self.max_image_pixels,
            self.max_image_frames,
            self.max_document_canvases,
        ) <= 0:
            raise ValueError("canvas limits must be positive")


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
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _pdf_canvases(content: bytes, limits: CanvasLimits) -> list[Canvas]:
    import pymupdf

    document = pymupdf.open(stream=content, filetype="pdf")
    try:
        if document.needs_pass or (
            getattr(document, "is_encrypted", False) and not document.authenticate("")
        ):
            raise InputPreparationError(
                "DOCUMENT_ENCRYPTED", "PDF 受密码保护，无法建立画布"
            )
        if len(document) == 0:
            raise InputPreparationError("DOCUMENT_EMPTY", "PDF 不包含页面")
        if len(document) > limits.max_document_canvases:
            raise InputPreparationError(
                "CANVAS_LIMIT_EXCEEDED",
                "PDF 页面数量超过安全上限",
                http_status=413,
            )

        canvases = []
        for index, page in enumerate(document, start=1):
            rect = page.rect
            mediabox = page.mediabox
            canvases.append(
                Canvas(
                    canvas_id=f"page:{index}",
                    kind=CanvasKind.PAGE,
                    source_index=index,
                    width=float(rect.width),
                    height=float(rect.height),
                    unit=CoordinateUnit.PT,
                    rotation=int(page.rotation),
                    layout_mode=detect_layout_mode(page),
                    source_geometry=SourceGeometry(
                        unit=CoordinateUnit.PT,
                        bbox=(
                            float(mediabox.x0),
                            float(mediabox.y0),
                            float(mediabox.x1),
                            float(mediabox.y1),
                        ),
                        details={"page_number": index},
                    ),
                )
            )
        return canvases
    finally:
        document.close()


def _docx_canvases(content: bytes, limits: CanvasLimits) -> list[Canvas]:
    detect_input("input.docx", content)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    sections = root.findall(f".//{_qname(_WORD_NS, 'sectPr')}")
    if not sections:
        raise InputPreparationError(
            "CANVAS_EXTRACTION_FAILED", "DOCX 缺少 section 页面定义"
        )
    if len(sections) > limits.max_document_canvases:
        raise InputPreparationError(
            "CANVAS_LIMIT_EXCEEDED",
            "DOCX section 数量超过安全上限",
            http_status=413,
        )

    canvases = []
    for index, section in enumerate(sections, start=1):
        page_size = section.find(_qname(_WORD_NS, "pgSz"))
        width_twips = int(
            (page_size.get(_qname(_WORD_NS, "w")) if page_size is not None else None)
            or 12_240
        )
        height_twips = int(
            (page_size.get(_qname(_WORD_NS, "h")) if page_size is not None else None)
            or 15_840
        )
        columns = section.find(_qname(_WORD_NS, "cols"))
        column_count = int(
            (columns.get(_qname(_WORD_NS, "num")) if columns is not None else None)
            or 1
        )
        layout_mode = (
            LayoutMode.SINGLE
            if column_count == 1
            else LayoutMode.DOUBLE
            if column_count == 2
            else LayoutMode.MULTI
        )
        canvases.append(
            Canvas(
                canvas_id=f"section:{index}",
                kind=CanvasKind.SECTION,
                source_index=index,
                width=width_twips / 20.0,
                height=height_twips / 20.0,
                unit=CoordinateUnit.PT,
                rotation=0,
                layout_mode=layout_mode,
                source_geometry=SourceGeometry(
                    unit="TWIP",
                    bbox=(0.0, 0.0, float(width_twips), float(height_twips)),
                    details={"column_count": column_count},
                ),
            )
        )
    return canvases


def _pptx_canvases(content: bytes, limits: CanvasLimits) -> list[Canvas]:
    detect_input("input.pptx", content)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        presentation_xml = archive.read("ppt/presentation.xml")
    root = ElementTree.fromstring(presentation_xml)
    slide_size = root.find(_qname(_PRESENTATION_NS, "sldSz"))
    slide_ids = root.findall(
        f"./{_qname(_PRESENTATION_NS, 'sldIdLst')}/{_qname(_PRESENTATION_NS, 'sldId')}"
    )
    if slide_size is None or not slide_ids:
        raise InputPreparationError(
            "CANVAS_EXTRACTION_FAILED", "PPTX 缺少 slide size 或幻灯片"
        )
    if len(slide_ids) > limits.max_document_canvases:
        raise InputPreparationError(
            "CANVAS_LIMIT_EXCEEDED",
            "PPTX 幻灯片数量超过安全上限",
            http_status=413,
        )

    width_emu = int(slide_size.get("cx") or 0)
    height_emu = int(slide_size.get("cy") or 0)
    if width_emu <= 0 or height_emu <= 0:
        raise InputPreparationError(
            "CANVAS_EXTRACTION_FAILED", "PPTX 幻灯片尺寸无效"
        )
    return [
        Canvas(
            canvas_id=f"slide:{index}",
            kind=CanvasKind.SLIDE,
            source_index=index,
            width=width_emu / 12_700.0,
            height=height_emu / 12_700.0,
            unit=CoordinateUnit.PT,
            rotation=0,
            layout_mode=LayoutMode.FREEFORM,
            source_geometry=SourceGeometry(
                unit=CoordinateUnit.EMU,
                bbox=(0.0, 0.0, float(width_emu), float(height_emu)),
                details={"slide_number": index},
            ),
        )
        for index in range(1, len(slide_ids) + 1)
    ]


def _orientation_rotation(orientation: int) -> int:
    return {3: 180, 5: 90, 6: 90, 7: 270, 8: 270}.get(orientation, 0)


def _image_canvases(content: bytes, limits: CanvasLimits) -> list[Canvas]:
    from PIL import Image

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(content)) as image:
            frame_count = int(getattr(image, "n_frames", 1))
            if frame_count > limits.max_image_frames:
                raise InputPreparationError(
                    "IMAGE_FRAME_LIMIT_EXCEEDED",
                    "图片帧数超过安全上限",
                    http_status=413,
                )

            canvases = []
            total_pixels = 0
            for index in range(frame_count):
                image.seek(index)
                width, height = map(int, image.size)
                total_pixels += width * height
                if width <= 0 or height <= 0 or total_pixels > limits.max_image_pixels:
                    raise InputPreparationError(
                        "IMAGE_PIXEL_LIMIT_EXCEEDED",
                        "图片总像素超过安全上限",
                        http_status=413,
                    )
                orientation = int(image.getexif().get(274, 1) or 1)
                rotation = _orientation_rotation(orientation)
                canonical_width, canonical_height = (
                    (height, width) if orientation in {5, 6, 7, 8} else (width, height)
                )
                image.load()
                canvases.append(
                    Canvas(
                        canvas_id=f"page:{index + 1}",
                        kind=CanvasKind.PAGE,
                        source_index=index + 1,
                        width=float(canonical_width),
                        height=float(canonical_height),
                        unit=CoordinateUnit.PX,
                        rotation=rotation,
                        layout_mode=LayoutMode.FREEFORM,
                        source_geometry=SourceGeometry(
                            unit=CoordinateUnit.PX,
                            bbox=(0.0, 0.0, float(width), float(height)),
                            details={
                                "frame_index": index,
                                "frame_count": frame_count,
                                "exif_orientation": orientation,
                                "mode": image.mode,
                                "format": image.format,
                            },
                        ),
                    )
                )
            return canvases


def extract_canvases(
    source_format: SourceFormat,
    content: bytes,
    *,
    limits: CanvasLimits | None = None,
) -> list[Canvas]:
    """Extract empty canonical canvases without creating semantic objects."""

    active_limits = limits or CanvasLimits()
    try:
        if source_format is SourceFormat.PDF:
            return _pdf_canvases(content, active_limits)
        if source_format is SourceFormat.DOCX:
            return _docx_canvases(content, active_limits)
        if source_format is SourceFormat.PPTX:
            return _pptx_canvases(content, active_limits)
        if source_format in _IMAGE_FORMATS:
            return _image_canvases(content, active_limits)
    except InputPreparationError:
        raise
    except Exception as exc:
        raise InputPreparationError(
            "CANVAS_EXTRACTION_FAILED",
            f"{source_format.value} 画布解析失败",
        ) from exc

    capability = capability_for(source_format)
    raise InputPreparationError(
        "CANVAS_FORMAT_UNSUPPORTED",
        f"{capability.source_format.value} 不能直接建立 canonical canvas",
        http_status=415,
    )
