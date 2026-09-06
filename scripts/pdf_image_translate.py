# SPDX-License-Identifier: MPL-2.0
"""PLAN-027d：PDF 内嵌图翻译 SSOT（位图 XObject 解耦 + 矢量安全覆盖）。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 允许从本仓 scripts 加载
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_ROOT = _SCRIPTS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PDF_IMAGE_OVERLAY = os.environ.get("QYUNSLATION_PDF_IMAGE_OVERLAY", "1").lower() not in (
    "0",
    "false",
    "off",
)
SIDECAR_URL = os.environ.get("QYUNSLATION_OFFICE_URL", "http://127.0.0.1:8010")


@dataclass
class PdfImgManifest:
    source: str
    output: str = ""
    bitmap_translated: int = 0
    bitmap_skipped: int = 0
    vector_translated: int = 0
    vector_skipped: int = 0
    details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _load_policy():
    import importlib.util
    import sys

    path = _ROOT / "qyunslation" / "extensions" / "doc_image_policy.py"
    name = "doc_image_policy_ssot"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod  # dataclass 需要模块已注册
    spec.loader.exec_module(mod)
    return mod


def _translate_via_local(png_bytes: bytes, to_lang: str) -> tuple[bytes, int, dict]:
    """优先本地 translate_image_bytes；失败则尝试 sidecar HTTP。"""
    try:
        from qyunslation.extensions.image_translate import translate_image_bytes

        return translate_image_bytes(png_bytes, suffix=".png", to_lang=to_lang)
    except Exception as exc:
        logger.warning("local translate failed, try sidecar: %s", exc)
    try:
        import requests

        r = requests.post(
            f"{SIDECAR_URL}/service/image-translate",
            files={"file": ("img.png", png_bytes, "image/png")},
            data={"to_lang": to_lang},
            timeout=300,
        )
        if r.status_code == 200 and r.content:
            n = int(r.headers.get("X-Translated-Blocks") or "0")
            return r.content, n, {}
    except Exception as exc:
        logger.warning("sidecar translate failed: %s", exc)
    return png_bytes, 0, {}


def _pixmap_png(doc, xref: int) -> tuple[bytes, int, int]:
    import pymupdf

    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    w, h = pix.width, pix.height
    return pix.tobytes("png"), w, h


def _png_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(data)) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return 0, 0


def _collect_xref_occurrences(doc) -> dict[int, list[dict]]:
    """xref -> list of {page, bbox, page_frac}。"""
    occ: dict[int, list[dict]] = {}
    for pno in range(len(doc)):
        page = doc[pno]
        page_area = float(page.rect.width * page.rect.height) or 1.0
        for info in page.get_image_info(xrefs=True) or []:
            xref = int(info.get("xref") or 0)
            if not xref:
                continue
            bbox = info.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            dw, dh = float(x1 - x0), float(y1 - y0)
            frac = (dw * dh) / page_area
            occ.setdefault(xref, []).append(
                {
                    "page": pno,
                    "bbox": (x0, y0, x1, y1),
                    "w": dw,
                    "h": dh,
                    "page_frac": frac,
                }
            )
    return occ


def translate_pdf_images(
    src: Path | str,
    *,
    to_lang: str = "简体中文",
    progress_cb=None,
    dest: Path | str | None = None,
) -> Path:
    """位图 replace_image（单引用）+ 矢量 crop/insert_image；无可译图则原样返回 src。"""
    import pymupdf
    from pdf_figure_crop import crop_png, find_safe_vector_figures

    src = Path(src)
    if not PDF_IMAGE_OVERLAY:
        return src
    policy = _load_policy()

    dest_path = Path(dest) if dest else src.with_name(src.stem + ".imgtr.pdf")
    manifest = PdfImgManifest(source=str(src))
    doc = pymupdf.open(src)
    try:
        if getattr(doc, "is_encrypted", False) and not doc.authenticate(""):
            logger.warning("encrypted pdf, skip image translate")
            return src

        occ_map = _collect_xref_occurrences(doc)
        # 唯一 xref 列表
        xrefs = sorted(occ_map.keys())
        total_steps = len(xrefs) + max(1, len(doc))
        step = 0

        # —— 策略 A：位图 ——
        for xref in xrefs:
            step += 1
            if progress_cb:
                try:
                    progress_cb(step, total_steps)
                except Exception:
                    pass
            occurrences = occ_map[xref]
            # 取最大显示尺寸做门槛
            best = max(occurrences, key=lambda o: o["w"] * o["h"])
            try:
                png, ow, oh = _pixmap_png(doc, xref)
            except Exception as exc:
                manifest.bitmap_skipped += 1
                manifest.details.append(
                    {"xref": xref, "status": "skip", "reason": f"extract:{exc}"}
                )
                continue
            decision = policy.evaluate_image_candidate(
                png,
                display_width_pt=best["w"],
                display_height_pt=best["h"],
                target_lang=to_lang,
                page_frac=best["page_frac"],
            )
            if not decision.should_translate:
                manifest.bitmap_skipped += 1
                manifest.details.append(
                    {
                        "xref": xref,
                        "status": "skip",
                        "reason": decision.reason,
                        "occurrences": len(occurrences),
                    }
                )
                continue

            # 多引用：仅当所有出现位置都通过几何门槛才全局替换；否则逐页 overlay
            all_ok = True
            for o in occurrences:
                ok, reason = policy.evaluate_geometry(
                    display_width_pt=o["w"],
                    display_height_pt=o["h"],
                    page_frac=o["page_frac"],
                )
                if not ok:
                    all_ok = False
                    break

            new_png, n, qc = _translate_via_local(png, to_lang)
            if n <= 0 or new_png == png:
                manifest.bitmap_skipped += 1
                manifest.details.append(
                    {
                        "xref": xref,
                        "status": "skip",
                        "reason": (qc or {}).get("skipped") or "no_blocks",
                    }
                )
                continue
            nw, nh = _png_size(new_png)
            if nw and oh and (nw != ow or nh != oh):
                # 尺寸不一致：禁止 replace_image，改逐实例 overlay
                all_ok = False
                logger.warning(
                    "xref %s size changed %sx%s -> %sx%s, use overlay",
                    xref,
                    ow,
                    oh,
                    nw,
                    nh,
                )

            if len(occurrences) == 1 and all_ok and nw == ow and nh == oh:
                try:
                    # replace on the page that owns it
                    page = doc[occurrences[0]["page"]]
                    page.replace_image(xref, stream=new_png)
                    manifest.bitmap_translated += 1
                    manifest.details.append(
                        {
                            "xref": xref,
                            "status": "replaced",
                            "blocks": n,
                            "occurrences": 1,
                        }
                    )
                except Exception as exc:
                    manifest.bitmap_skipped += 1
                    manifest.details.append(
                        {"xref": xref, "status": "fail", "reason": str(exc)}
                    )
            else:
                # 多引用或尺寸变化：逐实例 insert_image 覆盖（不改共享 xref）
                ok_n = 0
                for o in occurrences:
                    ok, reason = policy.evaluate_geometry(
                        display_width_pt=o["w"],
                        display_height_pt=o["h"],
                        page_frac=o["page_frac"],
                    )
                    if not ok:
                        continue
                    try:
                        page = doc[o["page"]]
                        import pymupdf as fitz

                        rect = fitz.Rect(*o["bbox"])
                        page.insert_image(
                            rect,
                            stream=new_png,
                            overlay=True,
                            keep_proportion=False,
                        )
                        ok_n += 1
                    except Exception as exc:
                        logger.warning("overlay xref %s page %s: %s", xref, o["page"], exc)
                if ok_n:
                    manifest.bitmap_translated += 1
                    manifest.details.append(
                        {
                            "xref": xref,
                            "status": "overlay_instances",
                            "blocks": n,
                            "instances": ok_n,
                            "occurrences": len(occurrences),
                        }
                    )
                else:
                    manifest.bitmap_skipped += 1

        # —— 策略 B：矢量 ——
        for pno in range(len(doc)):
            step += 1
            if progress_cb:
                try:
                    progress_cb(step, total_steps)
                except Exception:
                    pass
            page = doc[pno]
            # 排除本页已有位图 bbox
            exclude = []
            for info in page.get_image_info(xrefs=True) or []:
                if info.get("bbox"):
                    exclude.append(info["bbox"])
            try:
                figures = find_safe_vector_figures(page, exclude_rects=exclude)
            except Exception as exc:
                logger.warning("vector detect page %s: %s", pno, exc)
                continue
            for fi, rect in enumerate(figures):
                try:
                    png = crop_png(page, rect)
                except Exception as exc:
                    manifest.vector_skipped += 1
                    manifest.details.append(
                        {
                            "page": pno + 1,
                            "status": "vector_skip",
                            "reason": f"crop:{exc}",
                        }
                    )
                    continue
                decision = policy.evaluate_image_candidate(
                    png,
                    display_width_pt=float(rect.width),
                    display_height_pt=float(rect.height),
                    target_lang=to_lang,
                    page_frac=abs(rect.width * rect.height)
                    / (abs(page.rect.width * page.rect.height) or 1),
                )
                if not decision.should_translate:
                    manifest.vector_skipped += 1
                    continue
                new_png, n, qc = _translate_via_local(png, to_lang)
                if n <= 0:
                    manifest.vector_skipped += 1
                    continue
                try:
                    page.insert_image(
                        rect,
                        stream=new_png,
                        overlay=True,
                        keep_proportion=False,
                    )
                    manifest.vector_translated += 1
                    manifest.details.append(
                        {
                            "page": pno + 1,
                            "status": "vector_overlay",
                            "blocks": n,
                            "bbox": [round(x, 1) for x in (rect.x0, rect.y0, rect.x1, rect.y1)],
                        }
                    )
                except Exception as exc:
                    manifest.vector_skipped += 1
                    manifest.details.append(
                        {
                            "page": pno + 1,
                            "status": "vector_fail",
                            "reason": str(exc),
                        }
                    )

        if (
            manifest.bitmap_translated == 0
            and manifest.vector_translated == 0
        ):
            doc.close()
            return src

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest_path, garbage=3, deflate=True)
        manifest.output = str(dest_path)
    finally:
        try:
            doc.close()
        except Exception:
            pass

    try:
        mf = Path(str(src) + ".imgtr.json")
        mf.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("write pdf imgtr.json failed: %s", exc)

    return dest_path if dest_path.is_file() else src


if __name__ == "__main__":
    import sys as _sys

    logging.basicConfig(level=logging.INFO)
    src = Path(_sys.argv[1])
    lang = _sys.argv[2] if len(_sys.argv) > 2 else "简体中文"
    out = translate_pdf_images(src, to_lang=lang)
    print(out)
