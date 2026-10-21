# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: 送翻译前的源 PDF 修复（同名副本）与译后收尾。全部 fail-open。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

SIDECAR = "dropcaps.json"


def prepare_source(source: Path, workdir: Path) -> Path:
    """符号字体 ToUnicode 修复 → 首字下沉还原 → 横向整页转正。返回要送翻译的 PDF（可能就是 ``source``）。"""
    from qyunslation.structure.pdf_dropcap import normalize_dropcaps
    from qyunslation.structure.pdf_symbol_cmap import prepare_source_pdf

    original = source.resolve()
    current = prepare_source_pdf(source, workdir)
    # 双语左半（原件页）从 origin 还原：必须用已修复符号字体的副本，否则左侧会带回未修复字形。
    origin = original
    if current.resolve() != original:
        origin = workdir / f"origin-{source.name}"
        shutil.copyfile(current, origin)
    changed = False
    try:
        target = workdir / source.name
        records = normalize_dropcaps(current, target)
    except Exception:  # noqa: BLE001
        records = []
        target = current
    try:
        sidecar = workdir / SIDECAR
        if records:
            workdir.mkdir(parents=True, exist_ok=True)
            sidecar.write_text(
                json.dumps({"origin": str(origin), "records": [r.as_dict() for r in records]}, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            sidecar.unlink(missing_ok=True)
    except OSError:
        pass
    if records:
        current = target
    try:
        from qyunslation.structure.pdf_rotate import normalize_rotated_pages, write_sidecar

        rotated_target = workdir / source.name
        rotated = normalize_rotated_pages(current, rotated_target)
        write_sidecar(workdir, origin, rotated)
        if rotated:
            current = rotated_target
    except Exception:  # noqa: BLE001
        pass
    return current


def restore_symbol_left_halves(run_dir: Path, output_dir: Path) -> dict[str, Any] | None:
    """双语左半（原件页）有 U+0001 的页：脱敏旧文字层后，贴上已修复符号字体的原件页。转正页跳过。"""
    origins = sorted((run_dir / "source").glob("origin-*.pdf"))
    if not origins or not output_dir.is_dir():
        return None
    import pymupdf as fitz

    rotated_pages: set[int] = set()
    try:
        from qyunslation.structure.pdf_rotate import read_sidecar

        loaded = read_sidecar(run_dir / "source")
        if loaded is not None:
            rotated_pages = {rec.page for rec in loaded[1]}
    except Exception:  # noqa: BLE001
        pass
    out: dict[str, Any] = {}
    origin_doc = fitz.open(str(origins[0]))
    try:
        for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
            doc = fitz.open(str(pdf))
            try:
                pages: list[int] = []
                for index, page in enumerate(doc):
                    half = float(page.rect.width) / 2.0
                    if index in rotated_pages or index >= len(origin_doc) or half < 100:
                        continue
                    clip = fitz.Rect(0, 0, half, float(page.rect.height))
                    if "\x01" in page.get_text("text", clip=clip):
                        pages.append(index)
                for index in pages:
                    page = doc[index]
                    rect = fitz.Rect(0, 0, float(page.rect.width) / 2.0, float(page.rect.height))
                    page.add_redact_annot(rect)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
                    page.draw_rect(rect, color=None, fill=(1, 1, 1), width=0)
                    page.show_pdf_page(rect, origin_doc, index)
                if pages:
                    tmp = pdf.with_suffix(pdf.suffix + ".symtmp")
                    doc.save(str(tmp), garbage=3, deflate=True)
                    tmp.replace(pdf)
                out[pdf.name] = {"restored_pages": [index + 1 for index in pages]}
            finally:
                doc.close()
    finally:
        origin_doc.close()
    return out or None


def finish_translated_outputs(run_dir: Path, output_dir: Path) -> dict[str, Any] | None:
    """译后：首字下沉的中文首字放大 + 双语左半换回原件页；横向页转回原方向。任何异常都吞掉。"""
    if not output_dir.is_dir():
        return None
    out: dict[str, Any] = {}
    try:
        from qyunslation.structure.pdf_dropcap import DropCap, finish_dropcaps

        sidecar = run_dir / "source" / SIDECAR
        if sidecar.is_file():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            records = [DropCap(**item) for item in data.get("records", [])]
            origin = Path(data.get("origin") or "")
            for pdf in sorted(output_dir.glob("*.zh.mono.pdf")):
                out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=False)
            for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
                out[pdf.name] = finish_dropcaps(pdf, origin, records, dual=True)
    except Exception:  # noqa: BLE001
        pass
    # 双语左半含未修复符号字形（U+0001）的页：用已修复字体的原件页替换左半，并清掉旧文字层。
    try:
        sym = restore_symbol_left_halves(run_dir, output_dir)
        if sym:
            out.update({f"{name}:symbol": value for name, value in sym.items()})
    except Exception:  # noqa: BLE001
        pass
    # 转回原方向必须放在最后：上面的处理都按转正后的页面坐标。
    try:
        from qyunslation.structure.pdf_rotate import finish_rotated_pages, read_sidecar

        loaded = read_sidecar(run_dir / "source")
        if loaded is not None:
            origin, rotated = loaded
            for pdf in sorted(output_dir.glob("*.zh.mono.pdf")):
                out[pdf.name + ":rotate"] = finish_rotated_pages(pdf, origin, rotated, dual=False)
            for pdf in sorted(output_dir.glob("*.zh.dual.pdf")):
                out[pdf.name + ":rotate"] = finish_rotated_pages(pdf, origin, rotated, dual=True)
    except Exception:  # noqa: BLE001
        pass
    return out or None
