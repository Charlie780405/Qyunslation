"""Generate small, deterministic PLAN-030 structure fixtures.

The generated binaries are intentionally not committed. Their SHA-256 values are
recorded in ``catalog.v1.json`` so generation drift fails loudly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Callable

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches as PptxInches


FIXED_TIME = datetime(2025, 1, 1, tzinfo=UTC)
ZIP_TIME = (2025, 1, 1, 0, 0, 0)


def _pdf_bytes(*, columns: int) -> bytes:
    if columns not in {1, 2}:
        raise ValueError("columns must be 1 or 2")

    title = "Single-column research article" if columns == 1 else "Double-column review"
    text_positions = (
        [(72, 700, "Body text follows reading order across one column.")]
        if columns == 1
        else [
            (72, 700, "Left column body text and citation 1."),
            (324, 700, "Right column body text and citation 2."),
        ]
    )
    commands = [
        "BT /F1 18 Tf 72 752 Td (" + title + ") Tj ET",
        *[
            f"BT /F1 10 Tf {x} {y} Td ({text}) Tj ET"
            for x, y, text in text_positions
        ],
        "0.7 w 72 420 468 190 re S",
        "BT /F1 10 Tf 72 404 Td (Figure 1. Cross-column result.) Tj ET",
        "72 250 468 120 re S",
        "72 290 m 540 290 l S",
        "306 250 m 306 370 l S",
        "BT /F1 10 Tf 72 234 Td (Table 1. Structured outcomes.) Tj ET",
    ]
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _base_image(*, poster: bool = False, alpha: bool = False) -> Image.Image:
    size = (900, 1200) if poster else (320, 180)
    mode = "RGBA" if alpha else "RGB"
    background = (246, 248, 252, 0 if alpha else 255) if alpha else (246, 248, 252)
    image = Image.new(mode, size, background)
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((16, 16, width - 16, height - 16), outline=(11, 95, 130), width=4)
    draw.rectangle((32, 48, width // 2 - 8, height - 48), fill=(218, 238, 245))
    draw.rectangle((width // 2 + 8, 48, width - 32, height - 48), fill=(231, 239, 208))
    draw.text((32, 24), "PLAN-030 TRANSLATION FIXTURE", fill=(18, 42, 66))
    draw.text((48, 70), "Figure 1", fill=(18, 42, 66))
    draw.text((width // 2 + 24, 70), "Table 1", fill=(18, 42, 66))
    return image


def _save_image(image: Image.Image, format_name: str, **kwargs: object) -> bytes:
    stream = BytesIO()
    image.save(stream, format=format_name, **kwargs)
    return stream.getvalue()


def _png_bytes() -> bytes:
    return _save_image(_base_image(poster=True, alpha=True), "PNG", optimize=False)


def _jpeg_bytes() -> bytes:
    exif = Image.Exif()
    exif[274] = 6
    return _save_image(
        _base_image(),
        "JPEG",
        quality=85,
        subsampling=0,
        optimize=False,
        progressive=False,
        exif=exif,
    )


def _webp_bytes() -> bytes:
    return _save_image(_base_image(), "WEBP", lossless=True, method=6, exact=True)


def _bmp_bytes() -> bytes:
    return _save_image(_base_image(), "BMP")


def _tiff_bytes() -> bytes:
    first = _base_image()
    second = _base_image().transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    stream = BytesIO()
    first.save(
        stream,
        format="TIFF",
        save_all=True,
        append_images=[second],
        compression="raw",
    )
    return stream.getvalue()


def _canonicalize_ooxml(data: bytes) -> bytes:
    source = BytesIO(data)
    output = BytesIO()
    with zipfile.ZipFile(source, "r") as input_zip, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as output_zip:
        for name in sorted(input_zip.namelist()):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            output_zip.writestr(info, input_zip.read(name))
    return output.getvalue()


def _docx_bytes() -> bytes:
    document = Document()
    document.core_properties.title = "PLAN-030 deterministic review fixture"
    document.core_properties.created = FIXED_TIME
    document.core_properties.modified = FIXED_TIME

    section_properties = document.sections[0]._sectPr
    columns = section_properties.find(qn("w:cols"))
    if columns is None:
        columns = OxmlElement("w:cols")
        section_properties.append(columns)
    columns.set(qn("w:num"), "2")
    columns.set(qn("w:space"), "720")

    document.add_heading("Deterministic review", 0)
    document.add_paragraph("Two-column narrative with a native table and shared image part.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Outcome"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Stable"
    table.cell(1, 1).text = "Yes"

    image = _png_bytes()
    document.add_picture(BytesIO(image), width=Inches(2.2))
    document.add_paragraph("Figure 1. First occurrence.")
    document.add_picture(BytesIO(image), width=Inches(1.6))
    document.add_paragraph("Figure 1. Reused occurrence.")

    stream = BytesIO()
    document.save(stream)
    return _canonicalize_ooxml(stream.getvalue())


def _pptx_bytes() -> bytes:
    presentation = Presentation()
    presentation.core_properties.title = "PLAN-030 deterministic presentation fixture"
    presentation.core_properties.created = FIXED_TIME
    presentation.core_properties.modified = FIXED_TIME
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])

    title = slide.shapes.add_textbox(
        PptxInches(0.5), PptxInches(0.3), PptxInches(9), PptxInches(0.7)
    )
    title.text_frame.text = "Native slide text"
    table = slide.shapes.add_table(
        2, 2, PptxInches(0.5), PptxInches(1.3), PptxInches(4), PptxInches(2)
    ).table
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Coverage"
    table.cell(1, 1).text = "100%"
    slide.shapes.add_picture(
        BytesIO(_png_bytes()),
        PptxInches(5),
        PptxInches(1.3),
        width=PptxInches(4),
    )

    stream = BytesIO()
    presentation.save(stream)
    return _canonicalize_ooxml(stream.getvalue())


GENERATORS: dict[str, Callable[[], bytes]] = {
    "single-column.pdf": lambda: _pdf_bytes(columns=1),
    "double-column.pdf": lambda: _pdf_bytes(columns=2),
    "review.docx": _docx_bytes,
    "poster.png": _png_bytes,
    "photo.jpg": _jpeg_bytes,
    "diagram.webp": _webp_bytes,
    "scan.bmp": _bmp_bytes,
    "multipage.tiff": _tiff_bytes,
    "presentation.pptx": _pptx_bytes,
}


def generate_all(output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for relative_path, generator in GENERATORS.items():
        data = generator()
        target = output_dir / relative_path
        target.write_bytes(data)
        hashes[relative_path] = hashlib.sha256(data).hexdigest()
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate_all(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
