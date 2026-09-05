# SPDX-License-Identifier: MPL-2.0
"""原文 PDF → Markdown（HPD 视觉解析，降级 pypdf 纯文本）。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Hashable

from qyunslation.converter.x2md.base import X2MarkdownConverter, X2MarkdownConverterConfig
from qyunslation.ir.document import Document
from qyunslation.ir.markdown_document import MarkdownDocument

logger = logging.getLogger(__name__)

HPD_URL = os.environ.get("QYUNSLATION_HPD_URL", "http://100.67.66.123:8120")


@dataclass(kw_only=True)
class ConverterHpdConfig(X2MarkdownConverterConfig):
    hpd_url: str = HPD_URL
    dpi: int = 150
    min_native_chars: int = 200

    def gethash(self) -> Hashable:
        return self.hpd_url, self.dpi, self.min_native_chars


def _hpd_parse_image(url: str, image_b64: str, timeout: int = 180) -> str:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/parse",
        data=json.dumps({"image_b64": image_b64}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return (data.get("markdown") or "").strip()


def _native_pdf_text(path: Path) -> str:
    try:
        import pymupdf
    except ImportError:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)

    doc = pymupdf.open(path)
    try:
        return "\n\n".join((page.get_text("text") or "").strip() for page in doc)
    finally:
        doc.close()


def _hpd_pdf_to_markdown(path: Path, *, url: str, dpi: int) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    parts: list[str] = []
    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
            try:
                md = _hpd_parse_image(url, b64)
            except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                logger.warning("HPD 第 %s 页失败: %s", i + 1, exc)
                md = (page.get_text("text") or "").strip()
            if md:
                if i > 0:
                    parts.append(f"\n\n<!-- page {i + 1} -->\n\n")
                parts.append(md)
    finally:
        doc.close()
    return "".join(parts).strip()


def pdf_bytes_to_markdown(
    content: bytes,
    *,
    stem: str = "document",
    config: ConverterHpdConfig | None = None,
) -> str:
    cfg = config or ConverterHpdConfig()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{stem}.pdf"
        path.write_bytes(content)
        native = _native_pdf_text(path)
        if len(native.strip()) >= cfg.min_native_chars:
            # 可抽取文本的数字 PDF：优先 anydoc（与 Hermes 入库一致），否则原生文本
            try:
                import anydoc

                return anydoc.to_markdown(str(path))
            except Exception:
                return native
        return _hpd_pdf_to_markdown(path, url=cfg.hpd_url, dpi=cfg.dpi)


class ConverterHpd(X2MarkdownConverter):
    def __init__(self, config: ConverterHpdConfig | None = None):
        self.config = config or ConverterHpdConfig()
        super().__init__(config=self.config)

    def convert(self, document: Document) -> MarkdownDocument:
        md = pdf_bytes_to_markdown(
            document.content,
            stem=document.stem or "document",
            config=self.config,
        )
        return MarkdownDocument.from_bytes(
            md.encode("utf-8"), suffix=".md", stem=document.stem
        )

    async def convert_async(self, document: Document) -> MarkdownDocument:
        return await asyncio.to_thread(self.convert, document)

    def support_format(self) -> list[str]:
        return [".pdf"]
