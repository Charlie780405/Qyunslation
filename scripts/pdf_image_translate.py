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


def detail_with_qc(detail: dict, qc: dict | None) -> dict:
    payload = dict(detail)
    if not isinstance(qc, dict):
        return payload
    payload["object_qc"] = list(qc.get("object_qc") or [])
    if qc.get("dpi"):
        payload["dpi"] = qc["dpi"]
    return payload


def image_status_from_qc(object_qc: list[str] | None) -> str:
    from qyunslation.structure.role_fitter import HARD_FAIL

    codes = list(object_qc or [])
    if any(code in HARD_FAIL for code in codes):
        return "FAILED_HARD"
    return "TRANSLATED"


def _image_checks(qc: dict | None) -> dict:
    if not isinstance(qc, dict):
        return {}
    out = {}
    if qc.get("object_qc"):
        out["object_qc"] = list(qc["object_qc"])
    if qc.get("dpi"):
        out["dpi"] = qc["dpi"]
    return out


def _mark_image(obj, qc, *, fallback_reason: str | None = None) -> str:
    status = image_status_from_qc(list((qc or {}).get("object_qc") or []))
    reason = "object_qc_hard" if status == "FAILED_HARD" else fallback_reason
    if obj is not None:
        _mark(obj, status, reason, checks=_image_checks(qc))
    return status


def _mark_figures_for_bitmap(structure_manifest, occurrences: list[dict], qc) -> None:
    if structure_manifest is None:
        return
    import pymupdf

    from qyunslation.structure.models import ExecutionStatus, ObjectType

    for occ in occurrences:
        cover = pymupdf.Rect(*occ["bbox"])
        canvas_id = f"page:{int(occ['page']) + 1}"
        for obj in structure_manifest.objects:
            if obj.canvas_id != canvas_id or obj.type not in (ObjectType.FIGURE, ObjectType.IMAGE):
                continue
            if obj.execution_status is not ExecutionStatus.PENDING:
                continue
            box = obj.bbox
            rect = pymupdf.Rect(box.x0, box.y0, box.x1, box.y1)
            if rect.is_empty or abs(rect) <= 0:
                continue
            if abs(rect & cover) / abs(rect) >= BITMAP_COVER_FRAC:
                _mark_image(obj, qc)


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


def has_local_ocr() -> bool:
    """RapidOCR 是否可用。

    pdf2zh 与 qyunslation 是两个独立 venv，只有后者装了 rapidocr。缺失时
    image_translate 会静默回退到弱得多的 HPD 检测器（不抛异常），导致嵌字
    结果劣化却无人察觉，因此这里显式判定能力，无能力就交给 sidecar。
    """
    from importlib.util import find_spec

    try:
        return find_spec("rapidocr") is not None
    except Exception:
        return False


def _translate_via_local(png_bytes: bytes, to_lang: str) -> tuple[bytes, int, dict]:
    """有本地 OCR 能力时就地翻译；否则（或失败时）走 sidecar HTTP。"""
    if has_local_ocr():
        try:
            from qyunslation.extensions.image_translate import translate_image_bytes

            return translate_image_bytes(png_bytes, suffix=".png", to_lang=to_lang)
        except Exception as exc:
            logger.warning("local translate failed, try sidecar: %s", exc)
    else:
        logger.info("no local rapidocr, routing image translate to sidecar")
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


def _upsample_if_below_target(policy, png, width_pt, height_pt, to_lang, new_png, n, qc):
    from qyunslation.structure.role_fitter import QC_FONT_BELOW_TARGET

    codes = list((qc or {}).get("object_qc") or [])
    if QC_FONT_BELOW_TARGET not in codes or n <= 0:
        return new_png, n, qc
    best_png, best_n, best_qc = new_png, n, qc
    for dpi in (450, 600):
        boosted = policy.ensure_display_dpi(png, width_pt, height_pt, target_dpi=dpi)
        again, n2, qc2 = _translate_via_local(boosted, to_lang)
        if n2 <= 0:
            continue
        merged = dict(qc2 or {})
        merged["dpi"] = dpi
        merged["object_qc"] = list(merged.get("object_qc") or [])
        best_png, best_n, best_qc = again, n2, merged
        if QC_FONT_BELOW_TARGET not in merged["object_qc"]:
            return again, n2, merged
    return best_png, best_n, best_qc


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


BITMAP_COVER_FRAC = 0.80


def _structure_regions(
    structure_manifest, page_no: int, page, exclude_rects=None
) -> list | None:
    """从 manifest 取该页计划执行的 (对象, rect)；无 manifest 返回 None。

    PLAN-030d：执行侧不再重新检测，改用预扫描已固化的对象集，保证 UI 与执行同源。
    与位图 xref 重合的对象由策略 A 处理，这里标注跳过，避免同一张图被翻译两次。
    """
    if structure_manifest is None:
        return None
    import pymupdf

    from qyunslation.structure.models import ExecutionStatus, ObjectType

    covers = [pymupdf.Rect(r) for r in (exclude_rects or [])]
    canvas_id = f"page:{page_no}"
    out = []
    for obj in structure_manifest.objects:
        if obj.canvas_id != canvas_id:
            continue
        if obj.type not in (ObjectType.FIGURE, ObjectType.IMAGE):
            continue
        if obj.execution_status is not ExecutionStatus.PENDING:
            continue
        box = obj.bbox
        rect = pymupdf.Rect(box.x0, box.y0, box.x1, box.y1) & page.rect
        if rect.is_empty or abs(rect) <= 0:
            _mark(obj, "FAILED_SOFT", "bbox_outside_page")
            continue
        if any(abs(rect & c) / abs(rect) >= BITMAP_COVER_FRAC for c in covers):
            continue
        out.append((obj, rect))
    return out


def _mark(obj, status: str, reason: str | None = None, *, checks: dict | None = None) -> None:
    from qyunslation.structure.execution_evidence import write_output_evidence
    from qyunslation.structure.models import ExecutionStatus

    write_output_evidence(
        obj,
        status=ExecutionStatus(status),
        reason_code=reason,
        checks=checks or {},
    )


def _region_allowed(
    bbox: tuple[float, float, float, float],
    page,
    *,
    page_no: int,
    x_min_frac: float | None,
    page_parity: str | None,
) -> bool:
    """PLAN-033c：双语页只动右侧（或交替页的译文页）。"""
    if page_parity == "even" and page_no % 2 != 0:
        return False
    if page_parity == "odd" and page_no % 2 != 1:
        return False
    if x_min_frac is None:
        return True
    width = float(page.rect.width) or 1.0
    return ((bbox[0] + bbox[2]) / 2.0) / width >= x_min_frac


def translate_pdf_images(
    src: Path | str,
    *,
    to_lang: str = "简体中文",
    progress_cb=None,
    dest: Path | str | None = None,
    structure_manifest=None,
    x_min_frac: float | None = None,
    page_parity: str | None = None,
) -> Path:
    """位图 replace_image（单引用）+ 矢量 crop/insert_image；无可译图则原样返回 src。

    structure_manifest 为 None 时行为与 PLAN-030c 完全一致（回滚路径）；传入时按
    manifest 对象执行并回写终态。

    x_min_frac / page_parity 只限制处理范围，不改提取逻辑：双语并排页用
    x_min_frac=0.5 只动右侧；交替页双语用 page_parity='even'|'odd'。
    """
    import pymupdf
    from pdf_figure_crop import crop_png, translatable_regions

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
            _persist_structure_manifest(structure_manifest, reason="encrypted")
            return src

        occ_map = _collect_xref_occurrences(doc)
        if x_min_frac is not None or page_parity is not None:
            filtered: dict[int, list[dict]] = {}
            for xref, items in occ_map.items():
                kept = [
                    item
                    for item in items
                    if _region_allowed(
                        item["bbox"],
                        doc[item["page"]],
                        page_no=item["page"],
                        x_min_frac=x_min_frac,
                        page_parity=page_parity,
                    )
                ]
                if kept:
                    filtered[xref] = kept
            occ_map = filtered
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

            new_png, n, qc = _translate_via_local(
                policy.ensure_display_dpi(png, best["w"], best["h"]),
                to_lang,
            )
            new_png, n, qc = _upsample_if_below_target(
                policy, png, best["w"], best["h"], to_lang, new_png, n, qc
            )
            if n <= 0:
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
                # 尺寸不一致（含 300 DPI 升采样）：禁止 replace_image，改逐实例 overlay
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
                    status = image_status_from_qc(list((qc or {}).get("object_qc") or []))
                    if status == "FAILED_HARD":
                        manifest.bitmap_skipped += 1
                    else:
                        manifest.bitmap_translated += 1
                    manifest.details.append(
                        detail_with_qc(
                            {
                                "xref": xref,
                                "status": "replaced",
                                "blocks": n,
                                "occurrences": 1,
                            },
                            qc,
                        )
                    )
                    _mark_figures_for_bitmap(structure_manifest, occurrences, qc)
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
                    status = image_status_from_qc(list((qc or {}).get("object_qc") or []))
                    if status == "FAILED_HARD":
                        manifest.bitmap_skipped += 1
                    else:
                        manifest.bitmap_translated += 1
                    manifest.details.append(
                        detail_with_qc(
                            {
                                "xref": xref,
                                "status": "overlay_instances",
                                "blocks": n,
                                "instances": ok_n,
                                "occurrences": len(occurrences),
                            },
                            qc,
                        )
                    )
                    _mark_figures_for_bitmap(structure_manifest, occurrences, qc)
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
            if page_parity == "even" and pno % 2 != 0:
                continue
            if page_parity == "odd" and pno % 2 != 1:
                continue
            # 排除本页已有位图 bbox
            exclude = []
            for info in page.get_image_info(xrefs=True) or []:
                if info.get("bbox"):
                    exclude.append(info["bbox"])
            planned = _structure_regions(structure_manifest, pno + 1, page, exclude)
            if planned is None:
                try:
                    planned = [
                        (None, r) for r in translatable_regions(page, exclude_rects=exclude)
                    ]
                except Exception as exc:
                    logger.warning("vector detect page %s: %s", pno, exc)
                    continue
            for fi, (obj, rect) in enumerate(planned):
                if x_min_frac is not None and not _region_allowed(
                    (rect.x0, rect.y0, rect.x1, rect.y1),
                    page,
                    page_no=pno,
                    x_min_frac=x_min_frac,
                    page_parity=None,
                ):
                    continue
                try:
                    png = crop_png(page, rect)
                except Exception as exc:
                    manifest.vector_skipped += 1
                    if obj is not None:
                        _mark(obj, "FAILED_SOFT", "crop_failed")
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
                    if obj is not None:
                        _mark(obj, "EXPLICITLY_SKIPPED", "policy_declined")
                    continue
                new_png, n, qc = _translate_via_local(png, to_lang)
                new_png, n, qc = _upsample_if_below_target(
                    policy, png, float(rect.width), float(rect.height), to_lang, new_png, n, qc
                )
                if n <= 0:
                    manifest.vector_skipped += 1
                    if obj is not None:
                        _mark(obj, "EXPLICITLY_SKIPPED", "no_translatable_text")
                    continue
                try:
                    page.insert_image(
                        rect,
                        stream=new_png,
                        overlay=True,
                        keep_proportion=False,
                    )
                    status = _mark_image(obj, qc)
                    if status == "FAILED_HARD":
                        manifest.vector_skipped += 1
                    else:
                        manifest.vector_translated += 1
                    manifest.details.append(
                        detail_with_qc(
                            {
                                "page": pno + 1,
                                "status": "vector_overlay",
                                "blocks": n,
                                "bbox": [round(x, 1) for x in (rect.x0, rect.y0, rect.x1, rect.y1)],
                            },
                            qc,
                        )
                    )
                except Exception as exc:
                    manifest.vector_skipped += 1
                    if obj is not None:
                        _mark(obj, "FAILED_SOFT", "overlay_failed")
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
            _persist_structure_manifest(structure_manifest)
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

    _persist_structure_manifest(structure_manifest)
    return dest_path if dest_path.is_file() else src


def _persist_structure_manifest(structure_manifest, *, reason: str = "not_reached") -> None:
    """回写执行终态。未被执行触及的对象记为跳过，避免 PENDING 残留。"""
    if structure_manifest is None:
        return
    try:
        from qyunslation.structure import ManifestStore
        from qyunslation.structure.models import ExecutionStatus, ObjectType

        for obj in structure_manifest.objects:
            if (
                obj.type in (ObjectType.FIGURE, ObjectType.IMAGE)
                and obj.execution_status is ExecutionStatus.PENDING
            ):
                _mark(obj, "EXPLICITLY_SKIPPED", reason)
        # 状态变更后 summary 必须重算，否则回读时 MANIFEST_SUMMARY_MISMATCH
        structure_manifest.refresh_summary()
        from qyunslation.structure.model_trace import apply_current_model_trace

        apply_current_model_trace(structure_manifest)
        # 写审计快照而非结构缓存：后者要保持可重复翻译
        ManifestStore().put_execution(structure_manifest)
    except Exception as exc:
        logger.warning("persist structure manifest failed: %s", exc)


if __name__ == "__main__":
    import sys as _sys

    logging.basicConfig(level=logging.INFO)
    src = Path(_sys.argv[1])
    lang = _sys.argv[2] if len(_sys.argv) > 2 else "简体中文"
    out = translate_pdf_images(src, to_lang=lang)
    print(out)
