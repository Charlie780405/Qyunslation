#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""扫描件 hpd-debug.json → 中文 Markdown / DOCX。"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("debug2md")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _box_y(item: dict) -> float:
    box = item.get("box") or [0, 0, 0, 0]
    try:
        return float(box[1])
    except (TypeError, IndexError, ValueError):
        return 0.0


def _item_text(item: dict, *, prefer_zh: bool = True) -> str:
    if prefer_zh:
        zh = (item.get("text_zh") or "").strip()
        if zh and _CJK_RE.search(zh):
            return zh
    return " ".join(((item.get("text") or "").split())).strip()


def debug_to_markdown(data: dict, *, prefer_zh: bool = True) -> str:
    pages = data.get("pages") or []
    lines: list[str] = []
    title_set = False
    for pi, page in enumerate(pages):
        items = sorted(page.get("items") or [], key=_box_y)
        if pi > 0:
            lines.append("")
            lines.append(f"<!-- page {pi + 1} -->")
            lines.append("")
        preamble: list[str] = []
        for it in items:
            role = (it.get("role") or "body").lower()
            text = _item_text(it, prefer_zh=prefer_zh)
            if not text:
                continue
            if role in {"header", "address"}:
                preamble.append(text)
                continue
            if role == "section":
                if preamble:
                    lines.extend(preamble)
                    lines.append("")
                    preamble = []
                if not title_set:
                    lines.append(f"# {text}")
                    title_set = True
                else:
                    lines.append(f"## {text}")
                lines.append("")
                continue
            if role in {"signature", "closing", "footer"}:
                if preamble:
                    lines.extend(preamble)
                    lines.append("")
                    preamble = []
                lines.append(text)
                lines.append("")
                continue
            # body / other
            if preamble:
                lines.extend(preamble)
                lines.append("")
                preamble = []
            lines.append(text)
            lines.append("")
        if preamble:
            lines.extend(preamble)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def md_to_docx_bytes(md: str) -> bytes:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from qyunslation.exporter.md.md2docx_exporter import (
        MD2DocxExporter,
        MD2DocxExporterConfig,
    )
    from qyunslation.ir.markdown_document import MarkdownDocument

    doc = MarkdownDocument.from_bytes(md.encode("utf-8"), suffix=".md", stem="export")
    exporter = MD2DocxExporter(MD2DocxExporterConfig(engine="auto"))
    return exporter.export(doc).content


def export_from_debug(
    debug_json: Path,
    *,
    dest_md: Path | None = None,
    dest_docx: Path | None = None,
    prefer_zh: bool = True,
) -> tuple[Path | None, Path | None]:
    debug_json = Path(debug_json)
    data = json.loads(debug_json.read_text(encoding="utf-8"))
    md = debug_to_markdown(data, prefer_zh=prefer_zh)
    stem = debug_json.name
    for suffix in (".pdf.hpd-debug.json", ".hpd-debug.json", ".json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = re.sub(r"\.hpd-ocr$", "", stem, flags=re.I)
    # FDA responses on PIND.hpd-ocr → FDA responses on PIND；导出名用 .zh.md
    out_dir = debug_json.parent
    md_path = dest_md or (out_dir / f"{stem}.zh.md")
    md_path.write_text(md, encoding="utf-8")
    docx_path = None
    if dest_docx is not False:
        target = dest_docx or (out_dir / f"{stem}.zh.docx")
        try:
            target.write_bytes(md_to_docx_bytes(md))
            docx_path = target
        except Exception as exc:
            logger.warning("DOCX 导出失败: %s", exc)
    return md_path, docx_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="hpd-debug.json → md/docx")
    p.add_argument("debug_json", type=Path)
    p.add_argument("--md", type=Path, default=None)
    p.add_argument("--docx", type=Path, default=None)
    p.add_argument("--no-docx", action="store_true")
    p.add_argument("--en", action="store_true", help="用原文 text 而非 text_zh")
    args = p.parse_args()
    md_path, docx_path = export_from_debug(
        args.debug_json,
        dest_md=args.md,
        dest_docx=False if args.no_docx else args.docx,
        prefer_zh=not args.en,
    )
    print(md_path)
    if docx_path:
        print(docx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
