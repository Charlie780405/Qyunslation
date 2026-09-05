#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""按需导出 Markdown / DOCX：扫描件走 debug2md，普通 PDF 走 HPD 解析 + LLM 翻译。"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

logger = logging.getLogger("export_md_docx")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _find_debug_json(session_dir: Path, stem_hint: str) -> Path | None:
    candidates = sorted(session_dir.glob("*.hpd-debug.json"))
    if not candidates:
        return None
    hint = stem_hint.lower()
    for c in candidates:
        if hint and hint in c.name.lower():
            return c
    return candidates[0]


def _find_source_pdf(session_dir: Path, stem: str) -> Path | None:
    direct = session_dir / f"{stem}.pdf"
    if direct.is_file():
        return direct
    # letter: stem may be xxx.hpd-ocr
    base = re.sub(r"\.hpd-ocr$", "", stem, flags=re.I)
    alt = session_dir / f"{base}.pdf"
    if alt.is_file():
        return alt
    pdfs = [
        p
        for p in session_dir.glob("*.pdf")
        if not any(
            x in p.name.lower()
            for x in (".mono.", ".dual.", "letter-mono", ".hpd-ocr", "all_")
        )
    ]
    return pdfs[0] if pdfs else None


def _md_to_docx(md: str, dest: Path) -> Path:
    from qyunslation.exporter.md.md2docx_exporter import (
        MD2DocxExporter,
        MD2DocxExporterConfig,
    )
    from qyunslation.ir.markdown_document import MarkdownDocument

    doc = MarkdownDocument.from_bytes(md.encode("utf-8"), suffix=".md", stem=dest.stem)
    out = MD2DocxExporter(MD2DocxExporterConfig(engine="auto")).export(doc)
    dest.write_bytes(out.content)
    return dest


def _translate_markdown(en_md: str) -> str:
    from letter_translate_prompt import translate_blocks

    glossary: list[tuple[str, str]] = []
    try:
        from kv_reinsert import _load_glossary

        glossary = _load_glossary()
    except Exception:
        pass

    # 按空行切段，保留标题行原样结构
    blocks = re.split(r"\n{2,}", en_md.strip())
    need_idx: list[int] = []
    need_text: list[str] = []
    for i, b in enumerate(blocks):
        t = b.strip()
        if not t or t.startswith("<!--"):
            continue
        if t.startswith("#"):
            # 标题：去掉 # 后翻译再拼回
            m = re.match(r"^(#{1,6})\s+(.*)$", t, re.S)
            if m and m.group(2).strip() and not _CJK_RE.search(m.group(2)):
                need_idx.append(i)
                need_text.append(m.group(2).strip())
            continue
        if _CJK_RE.search(t):
            continue
        need_idx.append(i)
        need_text.append(t)

    if need_text:
        zhs = translate_blocks(need_text, glossary=glossary)
        for i, zh in zip(need_idx, zhs):
            t = blocks[i].strip()
            m = re.match(r"^(#{1,6})\s+(.*)$", t, re.S)
            if m:
                blocks[i] = f"{m.group(1)} {zh}"
            else:
                blocks[i] = zh
    return "\n\n".join(blocks).rstrip() + "\n"


def export_formats(
    *,
    session_dir: Path,
    stem: str,
    want_md: bool = True,
    want_docx: bool = True,
    progress_cb=None,
) -> dict[str, Path | None]:
    """返回 {md, docx} 路径。"""
    session_dir = Path(session_dir)
    result: dict[str, Path | None] = {"md": None, "docx": None}
    if not want_md and not want_docx:
        return result

    def _tick(f: float, d: str) -> None:
        if progress_cb:
            progress_cb(f, d)

    debug = _find_debug_json(session_dir, stem)
    if debug and debug.is_file():
        _tick(0.2, "从 OCR debug 生成 Markdown")
        from debug2md import export_from_debug

        # stem for output: strip .hpd-ocr from debug stem for cleaner names
        base = re.sub(r"\.hpd-ocr$", "", stem, flags=re.I)
        md_dest = session_dir / f"{base}.zh.md"
        docx_dest = session_dir / f"{base}.zh.docx" if want_docx else None
        md_path, docx_path = export_from_debug(
            debug,
            dest_md=md_dest,
            dest_docx=docx_dest if want_docx else False,
        )
        result["md"] = md_path if want_md else None
        result["docx"] = docx_path if want_docx else None
        _tick(1.0, "Markdown/DOCX 完成")
        return result

    src = _find_source_pdf(session_dir, stem)
    if not src:
        logger.warning("未找到原文 PDF，跳过 md/docx：%s", session_dir)
        return result

    _tick(0.1, "解析原文为 Markdown")
    from qyunslation.converter.x2md.converter_hpd import (
        ConverterHpd,
        ConverterHpdConfig,
    )
    from qyunslation.ir.document import Document

    doc = Document.from_path(src)
    en_md = ConverterHpd(ConverterHpdConfig()).convert(doc).content.decode("utf-8")
    _tick(0.4, "翻译 Markdown")
    zh_md = _translate_markdown(en_md)
    base = re.sub(r"\.hpd-ocr$", "", stem, flags=re.I)
    md_path = session_dir / f"{base}.zh.md"
    if want_md:
        md_path.write_text(zh_md, encoding="utf-8")
        result["md"] = md_path
    if want_docx:
        _tick(0.85, "导出 DOCX")
        docx_path = session_dir / f"{base}.zh.docx"
        try:
            _md_to_docx(zh_md, docx_path)
            result["docx"] = docx_path
        except Exception as exc:
            logger.warning("DOCX 失败: %s", exc)
    _tick(1.0, "Markdown/DOCX 完成")
    return result


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", type=Path)
    ap.add_argument("--stem", required=True)
    ap.add_argument("--md", action="store_true", default=True)
    ap.add_argument("--docx", action="store_true", default=True)
    ap.add_argument("--no-md", action="store_true")
    ap.add_argument("--no-docx", action="store_true")
    args = ap.parse_args()
    out = export_formats(
        session_dir=args.session_dir,
        stem=args.stem,
        want_md=not args.no_md,
        want_docx=not args.no_docx,
    )
    print(out)
