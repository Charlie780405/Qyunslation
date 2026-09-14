# SPDX-License-Identifier: MPL-2.0
"""PLAN-027c：DOCX DrawingML 实例枚举与共享 ImagePart 解耦嵌字。"""
from __future__ import annotations

import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

logger = logging.getLogger(__name__)

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}
EMU_PER_PT = 12700.0

DOC_IMAGE_WORKERS = int(os.environ.get("QYUNSLATION_DOC_IMAGE_WORKERS", "3"))
DOC_IMAGE_TIMEOUT = int(os.environ.get("QYUNSLATION_DOC_IMAGE_TIMEOUT", "300"))


@dataclass
class DrawingOccurrence:
    container: str  # body | header | footer | footnotes | endnotes
    is_header: bool
    embed_rid: str
    blip_el: Any
    part: Any  # story part owning the relationship
    image_part: Any
    width_pt: float
    height_pt: float
    src_rect: tuple[str, str, str, str] | None = None


@dataclass
class OverlayManifest:
    document: str = ""
    total_embedded_images: int = 0
    processed_images: int = 0
    skipped_images: int = 0
    vector_skipped: int = 0
    details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "document": self.document,
            "total_embedded_images": self.total_embedded_images,
            "processed_images": self.processed_images,
            "skipped_images": self.skipped_images,
            "vector_skipped": self.vector_skipped,
            "details": self.details,
        }


def _extent_pt(drawing_el) -> tuple[float, float]:
    extent = drawing_el.find(".//wp:extent", NS)
    if extent is None:
        # fallback inline extent under wp:inline / wp:anchor already covered by .//
        return 0.0, 0.0
    try:
        cx = float(extent.get("cx") or 0)
        cy = float(extent.get("cy") or 0)
    except ValueError:
        return 0.0, 0.0
    return cx / EMU_PER_PT, cy / EMU_PER_PT


def _src_rect(blip_el) -> tuple[str, str, str, str] | None:
    parent = blip_el.getparent()
    if parent is None:
        return None
    # a:srcRect is sibling under a:blipFill
    rect = parent.find("a:srcRect", NS)
    if rect is None:
        return None
    return (
        rect.get("l") or "0",
        rect.get("t") or "0",
        rect.get("r") or "0",
        rect.get("b") or "0",
    )


def _iter_story_parts(doc) -> list[tuple[str, Any, bool]]:
    """返回 (container_name, part, is_header)。"""
    out: list[tuple[str, Any, bool]] = [("body", doc.part, False)]
    try:
        for section in doc.sections:
            try:
                out.append(("header", section.header.part, True))
            except Exception:
                pass
            try:
                out.append(("footer", section.footer.part, False))
            except Exception:
                pass
            try:
                if section.different_first_page_header_footer:
                    out.append(("header", section.first_page_header.part, True))
                    out.append(("footer", section.first_page_footer.part, False))
            except Exception:
                pass
    except Exception:
        pass
    # footnotes / endnotes if present as related parts
    try:
        for rel in doc.part.rels.values():
            rt = getattr(rel, "reltype", "") or ""
            if "footnotes" in rt:
                out.append(("footnotes", rel.target_part, False))
            elif "endnotes" in rt:
                out.append(("endnotes", rel.target_part, False))
    except Exception:
        pass
    return out


def enumerate_drawing_occurrences(doc) -> list[DrawingOccurrence]:
    occs: list[DrawingOccurrence] = []
    for container, part, is_header in _iter_story_parts(doc):
        try:
            root = part.element
        except Exception:
            continue
        try:
            drawings = root.findall(".//w:drawing", NS)
        except Exception:
            drawings = []
        for drawing in drawings:
            blips = drawing.findall(".//a:blip", NS)
            for blip in blips:
                rid = blip.get(f"{{{NS['r']}}}embed")
                if not rid:
                    continue
                try:
                    image_part = part.rels[rid].target_part
                except Exception:
                    continue
                w_pt, h_pt = _extent_pt(drawing)
                occs.append(
                    DrawingOccurrence(
                        container=container,
                        is_header=is_header,
                        embed_rid=rid,
                        blip_el=blip,
                        part=part,
                        image_part=image_part,
                        width_pt=w_pt,
                        height_pt=h_pt,
                        src_rect=_src_rect(blip),
                    )
                )
    return occs


def _ctype_suffix(ctype: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(ctype or "", ".png")


def _clone_image_part(story_part, image_part, new_blob: bytes):
    """新建 ImagePart，挂到 story_part.rels，返回新 rId。"""
    from io import BytesIO

    rId, _image = story_part.get_or_add_image(BytesIO(new_blob))
    return rId, None


def overlay_docx_embedded_images(
    doc,
    *,
    to_lang: str = "简体中文",
    glossary: dict[str, str] | None = None,
    progress_cb=None,
    document_name: str = "",
    manifest_path: Path | None = None,
) -> OverlayManifest:
    """实例级嵌字。单图失败保留原图。"""
    from qyunslation.extensions.doc_image_policy import evaluate_image_candidate
    from qyunslation.extensions.image_translate import translate_image_bytes

    if os.environ.get("QYUNSLATION_IMAGE_OVERLAY", "1").lower() in ("0", "false", "off"):
        return OverlayManifest(document=document_name)

    occs = enumerate_drawing_occurrences(doc)
    # 引用计数：image_part 对象 id
    ref_count: dict[int, int] = {}
    for o in occs:
        ref_count[id(o.image_part)] = ref_count.get(id(o.image_part), 0) + 1

    manifest = OverlayManifest(
        document=document_name,
        total_embedded_images=len(occs),
    )
    # 缓存：相同 blob hash → 译后结果（避免重复翻）
    blob_cache: dict[str, tuple[bytes, int, dict]] = {}

    # 先判定哪些要翻
    tasks: list[tuple[int, DrawingOccurrence, str]] = []
    for idx, occ in enumerate(occs):
        ctype = getattr(occ.image_part, "content_type", "") or ""
        if "emf" in ctype or "wmf" in ctype or ctype.endswith("x-emf"):
            manifest.vector_skipped += 1
            manifest.skipped_images += 1
            manifest.details.append(
                {
                    "image_index": idx + 1,
                    "container": occ.container,
                    "display_size_pt": [round(occ.width_pt, 1), round(occ.height_pt, 1)],
                    "status": "skipped",
                    "reason": "emf_wmf",
                }
            )
            continue
        try:
            blob = occ.image_part.blob
        except Exception as exc:
            manifest.skipped_images += 1
            manifest.details.append(
                {
                    "image_index": idx + 1,
                    "container": occ.container,
                    "status": "skipped",
                    "reason": f"blob_error:{exc}",
                }
            )
            continue
        decision = evaluate_image_candidate(
            blob,
            display_width_pt=occ.width_pt,
            display_height_pt=occ.height_pt,
            target_lang=to_lang,
            is_header=occ.is_header,
        )
        if not decision.should_translate and decision.reason not in ("ok",):
            # 几何未过：跳过；ok 但无 OCR 仍进入翻译阶段让 OCR 再判
            if decision.reason != "ok":
                manifest.skipped_images += 1
                manifest.details.append(
                    {
                        "image_index": idx + 1,
                        "container": occ.container,
                        "display_size_pt": [round(occ.width_pt, 1), round(occ.height_pt, 1)],
                        "status": "skipped",
                        "reason": decision.reason,
                    }
                )
                continue
        tasks.append((idx, occ, decision.feature_hash))

    total = len(tasks)
    workers = max(1, min(DOC_IMAGE_WORKERS, total or 1))

    def _worker(item: tuple[int, DrawingOccurrence, str]):
        idx, occ, fhash = item
        blob = occ.image_part.blob
        if fhash in blob_cache:
            return idx, occ, blob_cache[fhash], True
        ctype = getattr(occ.image_part, "content_type", "") or ""
        suffix = _ctype_suffix(ctype)
        t0 = time.time()
        from qyunslation.extensions.doc_image_policy import ensure_display_dpi

        work_blob = ensure_display_dpi(blob, occ.width_pt, occ.height_pt)
        overlay_kwargs = {"glossary": glossary} if glossary else {}
        new_blob, n, qc = translate_image_bytes(
            work_blob, suffix=suffix, to_lang=to_lang, **overlay_kwargs
        )
        # Preserve source bytes and attach an explicit DPI tag only to the
        # derived translated asset. Pixel upsampling has already happened in
        # ``work_blob`` when the display geometry requires it.
        from qyunslation.extensions.doc_image_policy import ensure_master_dpi

        new_blob = ensure_master_dpi(new_blob)
        qc = dict(qc or {})
        qc.setdefault("dpi", 300)
        elapsed = time.time() - t0
        result = (new_blob, n, {**(qc or {}), "elapsed": round(elapsed, 2)})
        blob_cache[fhash] = result
        return idx, occ, result, False

    done = 0
    results: list[tuple[int, DrawingOccurrence, tuple, bool]] = []
    if tasks:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_worker, t): t for t in tasks}
            for fut in as_completed(futs):
                done += 1
                if progress_cb:
                    try:
                        progress_cb(done, total)
                    except Exception:
                        pass
                try:
                    results.append(fut.result(timeout=DOC_IMAGE_TIMEOUT))
                except Exception as exc:
                    idx, occ, _ = futs[fut]
                    manifest.skipped_images += 1
                    manifest.details.append(
                        {
                            "image_index": idx + 1,
                            "container": occ.container,
                            "status": "failed",
                            "reason": str(exc),
                        }
                    )

    for idx, occ, (new_blob, n, qc), _cached in results:
        detail = {
            "image_index": idx + 1,
            "container": occ.container,
            "display_size_pt": [round(occ.width_pt, 1), round(occ.height_pt, 1)],
            "blocks_count": n,
            "qc_passed": bool((qc or {}).get("ok", True)) if qc else True,
            "elapsed": (qc or {}).get("elapsed"),
        }
        if n <= 0 or not new_blob or new_blob == occ.image_part.blob:
            # 无文字或已是目标语种等
            detail["status"] = "skipped"
            detail["reason"] = (qc or {}).get("skipped") or "no_blocks"
            manifest.skipped_images += 1
            manifest.details.append(detail)
            continue
        try:
            if ref_count.get(id(occ.image_part), 0) > 1:
                # 多引用：克隆新 part，只改当前 blip
                rId_new, _new_part = _clone_image_part(occ.part, occ.image_part, new_blob)
                occ.blip_el.set(f"{{{NS['r']}}}embed", rId_new)
                detail["status"] = "translated_cloned"
            else:
                occ.image_part._blob = new_blob
                detail["status"] = "translated"
            manifest.processed_images += 1
            manifest.details.append(detail)
        except Exception as exc:
            detail["status"] = "failed"
            detail["reason"] = f"writeback:{exc}"
            manifest.skipped_images += 1
            manifest.details.append(detail)
            logger.warning("docx image writeback failed: %s", exc)

    if manifest_path is not None:
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("write imgtr.json failed: %s", exc)

    return manifest
