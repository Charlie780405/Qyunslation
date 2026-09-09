# SPDX-License-Identifier: MPL-2.0
"""图片嵌字：RapidOCR 检测 → LLM 翻译 → opencv 擦除 → PIL 嵌字（PLAN-005c / PLAN-021）。"""
from __future__ import annotations

import base64
import csv
import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

OLLAMA = (
    os.environ.get("QYUNSLATION_BASE_URL")
    or os.environ.get("DOCUTRANSLATE_BASE_URL")
    or ""
).replace("/v1", "")
HPD_URL = os.environ.get("QYUNSLATION_HPD_BASE_URL") or ""
FONT = os.environ.get("QYUNSLATION_FONT") or ""
FONT_BOLD = os.environ.get("QYUNSLATION_FONT_BOLD") or ""
MODEL = (
    os.environ.get("QYUNSLATION_MODEL_ID")
    or os.environ.get("DOCUTRANSLATE_MODEL_ID")
    or "qwen3.6:35b-a3b"
)
GLOSSARY_CSV = os.environ.get("QYUNSLATION_GLOSSARY_CSV") or ""

OCR_MIN_SCORE = float(os.environ.get("QYUNSLATION_OCR_MIN_SCORE", "0.5"))
TRANSLATE_BATCH = int(os.environ.get("QYUNSLATION_TRANSLATE_BATCH", "25"))
NUM_PREDICT = int(os.environ.get("QYUNSLATION_NUM_PREDICT", "4096"))
CONTRAST_MIN = float(os.environ.get("QYUNSLATION_CONTRAST_MIN", "60"))
SOLID_STD_MAX = float(os.environ.get("QYUNSLATION_SOLID_STD_MAX", "12"))
SOLID_FRAC_MIN = float(os.environ.get("QYUNSLATION_SOLID_FRAC_MIN", "0.80"))
BOLD_AREA_RATIO = float(os.environ.get("QYUNSLATION_BOLD_AREA_RATIO", "0.28"))
AVAIL_W_MULT = float(os.environ.get("QYUNSLATION_AVAIL_W_MULT", "3.0"))
AVAIL_H_MULT = float(os.environ.get("QYUNSLATION_AVAIL_H_MULT", "1.6"))
AVAIL_BG_DELTA = float(os.environ.get("QYUNSLATION_AVAIL_BG_DELTA", "28"))
QC_STRICT = os.environ.get("QYUNSLATION_IMAGE_QC_STRICT", "0").lower() in (
    "1",
    "true",
    "on",
)
QC_INK_MIN = float(os.environ.get("QYUNSLATION_QC_INK_MIN", "0.005"))
# 无 draw_bbox 时不用大窗比例：短标签在流程图大盒里会假空白（与 C8/pitfall 21 同类）
QC_INK_MIN_PX = int(os.environ.get("QYUNSLATION_QC_INK_MIN_PX", "32"))
TIER_BG_STEP = int(os.environ.get("QYUNSLATION_TIER_BG_STEP", "24"))
TIER_OUTLIER_RATIO = float(os.environ.get("QYUNSLATION_TIER_OUTLIER_RATIO", "0.6"))
TIER_RATIO_TOL = float(os.environ.get("QYUNSLATION_TIER_RATIO_TOL", "0.02"))
ALIGN_TOL_PX = float(os.environ.get("QYUNSLATION_ALIGN_TOL_PX", "12"))
# 线状行判据：宽高比超此值且高度不足最高行此比例，视为括号线/色带而非文字
RULE_ROW_RATIO = float(os.environ.get("QYUNSLATION_RULE_ROW_RATIO", "8.0"))
RULE_ROW_H_FRAC = float(os.environ.get("QYUNSLATION_RULE_ROW_H_FRAC", "0.4"))
# 跨框左对齐组：左墨迹边差与纵向间距上限
LEFT_GROUP_TOL_PX = float(os.environ.get("QYUNSLATION_LEFT_GROUP_TOL_PX", "8"))
LEFT_GROUP_GAP_MULT = float(os.environ.get("QYUNSLATION_LEFT_GROUP_GAP_MULT", "1.6"))
# 实心填充纵向收敛到文字带时的上下 pad（PLAN-027g：加厚覆盖抗锯齿）
FILL_BAND_PAD = int(os.environ.get("QYUNSLATION_FILL_BAND_PAD", "4"))
# 擦除前 OCR 框外扩像素，盖住抗锯齿环
ERASE_PAD_PX = int(os.environ.get("QYUNSLATION_ERASE_PAD_PX", "3"))
# 贯穿线保护核相对框宽/高的比例
LINE_GUARD_FRAC = float(os.environ.get("QYUNSLATION_LINE_GUARD_FRAC", "0.6"))
# C10：OCR 框内文字带外「原图非背景→成品背景」像素超此数即失败
GRAPHICS_DAMAGE_MAX = int(os.environ.get("QYUNSLATION_GRAPHICS_DAMAGE_MAX", "40"))

OCR_ENGINE = (os.environ.get("QYUNSLATION_OCR_ENGINE") or "auto").strip().lower()

_RAPID_ENGINE = None
_OCR_STATUS_CACHE: dict | None = None


def _require_env(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}（图片嵌字需要显式配置，不再使用硬编码内网默认值）"
        )
    return value


def _ollama() -> str:
    return _require_env("DOCUTRANSLATE_BASE_URL / QYUNSLATION_BASE_URL", OLLAMA)


def _hpd_url() -> str:
    return _require_env("QYUNSLATION_HPD_BASE_URL", HPD_URL)


def _font() -> str:
    return _require_env("QYUNSLATION_FONT", FONT)


def _font_bold() -> str | None:
    """粗体字面；缺省时尝试 Regular 旁的 Bold.otf。"""
    if FONT_BOLD and Path(FONT_BOLD).is_file():
        return FONT_BOLD
    regular = FONT or ""
    if not regular:
        return None
    p = Path(regular)
    for cand in (
        p.with_name("NotoSansSC-Bold.otf"),
        p.with_name(p.stem.replace("Regular", "Bold") + p.suffix),
        p.parent / "NotoSansSC-Bold.otf",
    ):
        if cand.is_file():
            return str(cand)
    return None


_BLOCK_RE = re.compile(
    r"<BLOCK>(?P<type>\w+)\s+\[(?P<x1>\d+),\s*(?P<y1>\d+),\s*(?P<x2>\d+),\s*(?P<y2>\d+)\]"
    r"<CHILD>(?P<text>.+)$"
)


def _hpd_parse(image_b64: str, timeout: int = 180) -> str:
    req = urllib.request.Request(
        f"{_hpd_url().rstrip('/')}/parse",
        data=json.dumps({"image_b64": image_b64}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("markdown") or ""


def _blocks(raw: str) -> list[tuple[int, int, int, int, str]]:
    out = []
    for line in raw.splitlines():
        m = _BLOCK_RE.match(line.strip())
        if not m:
            continue
        text = m.group("text").strip()
        if not text or text == "[Non-Text]":
            continue
        if "<" in text:
            text = re.sub(r"<[^>]+>", " ", text)
            text = " ".join(text.split()).strip()
        if not text:
            continue
        out.append(
            (
                int(m.group("x1")),
                int(m.group("y1")),
                int(m.group("x2")),
                int(m.group("y2")),
                text,
            )
        )
    return out


def ocr_image_hpd(img_path: str | Path) -> list[tuple[int, int, int, int, str, float]]:
    """HPD 检测+识别 → [(x1,y1,x2,y2,text,score), ...]（回退路径）。"""
    img_path = Path(img_path)
    raw_bytes = img_path.read_bytes()
    b64 = base64.b64encode(raw_bytes).decode()
    md = _hpd_parse(b64)
    blocks = _blocks(md)
    img = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read image: {img_path}")
    h, w = img.shape[:2]
    max_x = max((b[2] for b in blocks), default=0)
    max_y = max((b[3] for b in blocks), default=0)
    # HPD 常返回 0–1000 归一化坐标
    if max(max_x, max_y) <= 1000 and (w > 1200 or h > 1200):
        sx, sy = w / 1000.0, h / 1000.0
    else:
        sx = sy = 1.0
    out = []
    for x1, y1, x2, y2, text in blocks:
        out.append(
            (
                int(x1 * sx),
                int(y1 * sy),
                int(max(x2 * sx, x1 * sx + 8)),
                int(max(y2 * sy, y1 * sy + 8)),
                text,
                1.0,
            )
        )
    out.sort(key=lambda b: (b[1], b[0]))
    return out


def _get_rapid_engine():
    global _RAPID_ENGINE
    if _RAPID_ENGINE is None:
        from rapidocr import RapidOCR

        _RAPID_ENGINE = RapidOCR()
    return _RAPID_ENGINE


def ocr_image_rapid(img_path: str | Path) -> list[tuple[int, int, int, int, str, float]]:
    """RapidOCR 检测+识别 → [(x1,y1,x2,y2,text,score), ...]（主路径，像素坐标）。"""
    img_path = Path(img_path)
    res = _get_rapid_engine()(str(img_path))
    boxes = getattr(res, "boxes", None)
    txts = getattr(res, "txts", None)
    scores = getattr(res, "scores", None)
    if txts is None or boxes is None:
        return []
    out: list[tuple[int, int, int, int, str, float]] = []
    for box, text, score in zip(boxes, txts, scores or [1.0] * len(txts)):
        text = (text or "").strip()
        if not text:
            continue
        sc = float(score) if score is not None else 1.0
        if sc < OCR_MIN_SCORE:
            continue
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        x1, y1 = int(min(xs)), int(min(ys))
        x2, y2 = int(max(xs)), int(max(ys))
        out.append((x1, y1, max(x2, x1 + 8), max(y2, y1 + 8), text, sc))
    out.sort(key=lambda b: (b[1], b[0]))
    return out


def ocr_image_vision(img_path: str | Path) -> list[tuple[int, int, int, int, str, float]]:
    """Vision OCR 接口位（PLAN-027f）。

    接入契约（未实现，禁止静默返回空列表）：
    - DeepSeek grounding / VL2 返回 ``<|det|>[[x1,y1,x2,y2]]``，坐标归一化到 0–999；
    - 换算：``px = int(coord / 999 * dim)``，dim 为原图宽或高；
    - 本机无 GPU，Ollama 仅有纯文本模型，故本函数当前固定抛 ``NotImplementedError``。
    """
    raise NotImplementedError(
        "ocr_image_vision is a PLAN-027f stub; set QYUNSLATION_OCR_ENGINE=auto|rapidocr|hpd"
    )


def ocr_engine_status(*, refresh: bool = False) -> dict:
    """探测各 OCR 后端能力。状态：ok / unavailable / failed / stub。

    RapidOCR 未安装（ImportError）与装了但运行失败必须分开，避免静默降级不可见。
    """
    global _OCR_STATUS_CACHE
    if _OCR_STATUS_CACHE is not None and not refresh:
        return dict(_OCR_STATUS_CACHE)

    status: dict = {
        "preferred": OCR_ENGINE or "auto",
        "engines": {},
    }

    # rapidocr
    try:
        from importlib.util import find_spec

        if find_spec("rapidocr") is None:
            status["engines"]["rapidocr"] = {
                "status": "unavailable",
                "detail": "module rapidocr not installed",
            }
        else:
            try:
                # 仅构造引擎，不跑图；构造失败（缺 onnxruntime 等）记为 failed
                _get_rapid_engine()
                status["engines"]["rapidocr"] = {"status": "ok", "detail": ""}
            except ImportError as exc:
                status["engines"]["rapidocr"] = {
                    "status": "unavailable",
                    "detail": str(exc),
                }
            except Exception as exc:
                status["engines"]["rapidocr"] = {
                    "status": "failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
    except Exception as exc:
        status["engines"]["rapidocr"] = {
            "status": "failed",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    # hpd：远程服务，有 URL 配置即视为可用入口（连通性在调用时判定）
    if HPD_URL:
        status["engines"]["hpd"] = {
            "status": "ok",
            "detail": f"endpoint configured: {HPD_URL}",
        }
    else:
        status["engines"]["hpd"] = {
            "status": "unavailable",
            "detail": "QYUNSLATION_HPD_BASE_URL not set",
        }

    status["engines"]["vision"] = {
        "status": "stub",
        "detail": "NotImplementedError until Vision grounding is wired",
    }

    _OCR_STATUS_CACHE = dict(status)
    return status


def ocr_image_with_engine(
    img_path: str | Path,
) -> tuple[list[tuple[int, int, int, int, str, float]], str]:
    """返回 (boxes, engine_actually_used)。

    QYUNSLATION_OCR_ENGINE:
      auto（默认）| rapidocr | hpd | vision
    auto：RapidOCR →（零块/不可用/失败）HPD；降级写 warning，不再静默。
    """
    img_path = Path(img_path)
    preferred = OCR_ENGINE or "auto"

    def _run_rapid() -> list[tuple[int, int, int, int, str, float]]:
        return ocr_image_rapid(img_path)

    def _run_hpd() -> list[tuple[int, int, int, int, str, float]]:
        return ocr_image_hpd(img_path)

    if preferred == "vision":
        # 绝不吞 NotImplementedError
        boxes = ocr_image_vision(img_path)
        return boxes, "vision"

    if preferred == "rapidocr":
        boxes = _run_rapid()
        logger.info("OCR RapidOCR (forced): %d boxes", len(boxes))
        return boxes, "rapidocr"

    if preferred == "hpd":
        boxes = _run_hpd()
        logger.info("OCR HPD (forced): %d boxes", len(boxes))
        return boxes, "hpd"

    # auto
    st = ocr_engine_status()
    rapid = (st.get("engines") or {}).get("rapidocr") or {}
    rapid_st = rapid.get("status")

    if rapid_st == "unavailable":
        logger.warning(
            "RapidOCR unavailable (%s); falling back to HPD",
            rapid.get("detail") or "not installed",
        )
        try:
            boxes = _run_hpd()
            logger.info("OCR HPD fallback: %d boxes", len(boxes))
            return boxes, "hpd"
        except Exception as exc:
            logger.warning("HPD OCR also failed: %s", exc)
            return [], "none"

    if rapid_st == "failed":
        logger.warning(
            "RapidOCR failed at init (%s); falling back to HPD",
            rapid.get("detail") or "unknown",
        )
        try:
            boxes = _run_hpd()
            logger.info("OCR HPD fallback: %d boxes", len(boxes))
            return boxes, "hpd"
        except Exception as exc:
            logger.warning("HPD OCR also failed: %s", exc)
            return [], "none"

    try:
        boxes = _run_rapid()
    except Exception as exc:
        logger.warning("RapidOCR failed, fallback HPD: %s", exc)
        boxes = []
        try:
            boxes = _run_hpd()
            logger.info("OCR HPD fallback: %d boxes", len(boxes))
            return boxes, "hpd"
        except Exception as exc2:
            logger.warning("HPD OCR also failed: %s", exc2)
            return [], "none"

    if boxes:
        logger.info("OCR RapidOCR: %d boxes", len(boxes))
        return boxes, "rapidocr"

    # 零块：仍尝试 HPD（扫描件场景），但显式记录降级
    logger.warning("RapidOCR returned 0 boxes; trying HPD fallback")
    try:
        boxes = _run_hpd()
        logger.info("OCR HPD fallback: %d boxes", len(boxes))
        return boxes, "hpd"
    except Exception as exc:
        logger.warning("HPD OCR also failed: %s", exc)
        return [], "rapidocr"


def ocr_image(img_path: str | Path) -> list[tuple[int, int, int, int, str, float]]:
    """主 OCR：兼容旧签名。内部走 ocr_image_with_engine。"""
    boxes, _engine = ocr_image_with_engine(img_path)
    return boxes


def _load_glossary() -> dict[str, str]:
    if not GLOSSARY_CSV:
        return {}
    path = Path(GLOSSARY_CSV)
    if not path.is_file():
        return {}
    d: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            s, t = (row.get("source") or "").strip(), (row.get("target") or "").strip()
            if s and t:
                d[s] = t
    return d


def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
    for src in sorted(glossary.keys(), key=len, reverse=True):
        if src in text:
            text = text.replace(src, glossary[src])
    return text


def _parse_numbered(content: str) -> dict[int, str]:
    content = re.sub(r"<think>[\s\S]*?</think>", "", content or "", flags=re.I).strip()
    trans: dict[int, str] = {}
    for line in content.split("\n"):
        m = re.match(r"(\d+)[.、)\s]+(.+)", line.strip())
        if m:
            trans[int(m.group(1))] = m.group(2).strip()
    return trans


def _chat(prompt: str, model: str, num_ctx: int) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": NUM_PREDICT},
    }
    req = urllib.request.Request(
        f"{_ollama()}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        msg = json.loads(r.read().decode()).get("message") or {}
    return (msg.get("content") or "").strip()


def _translate_one(text: str, target: str, model: str, num_ctx: int) -> str:
    prompt = (
        f"Translate the following text to {target}. "
        "Output ONLY the translation, no explanations:\n"
        f"{text}"
    )
    try:
        return _chat(prompt, model, num_ctx).strip()
    except Exception as exc:
        logger.warning("single-line retry failed: %s", exc)
        return ""


def translate_texts(
    texts: list[str],
    model: str = MODEL,
    num_ctx: int = 8192,
    to_lang: str = "简体中文",
) -> dict[int, str]:
    """批量翻译：think=false、分批、缺失条目单条重试。返回 1-based 编号 → 译文。"""
    if not texts:
        return {}
    glossary = _load_glossary()
    prepared = [_apply_glossary(t, glossary) for t in texts]
    target = (to_lang or "简体中文").strip() or "简体中文"
    result: dict[int, str] = {}
    batch_size = max(1, TRANSLATE_BATCH)
    parsed_total = 0
    retried = 0

    for start in range(0, len(prepared), batch_size):
        chunk = prepared[start : start + batch_size]
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chunk))
        prompt = (
            f"Translate each numbered line to {target}. "
            "Output ONLY the translation, keep the same numbering, no explanations:\n"
            f"{numbered}"
        )
        try:
            content = _chat(prompt, model, num_ctx)
            batch_map = _parse_numbered(content)
        except Exception as exc:
            logger.warning("batch translate failed at offset %d: %s", start, exc)
            batch_map = {}
        parsed_total += len(batch_map)

        for i, src in enumerate(chunk):
            global_idx = start + i + 1
            local_idx = i + 1
            zh = (batch_map.get(local_idx) or "").strip()
            if not zh:
                zh = _translate_one(src, target, model, num_ctx)
                if zh:
                    retried += 1
            if zh:
                result[global_idx] = zh

    logger.info(
        "translate_texts: requested=%d parsed=%d retried=%d final=%d to_lang=%s",
        len(texts),
        parsed_total,
        retried,
        len(result),
        target,
    )
    return result


def _median_bgr(pixels: np.ndarray) -> tuple[int, int, int]:
    if pixels.size == 0:
        return (17, 17, 17)
    med = np.median(pixels.reshape(-1, 3), axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def _gray_of(bgr: tuple[int, int, int]) -> float:
    return 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2]


def _analyze_box_style(roi: np.ndarray) -> dict:
    """Otsu 分层取背景/文字色、按通道纯色判定、粗细与水平对齐（PLAN-022/023）。"""
    if roi.size == 0:
        return {
            "bg_bgr": (240, 240, 240),
            "fg_bgr": (17, 17, 17),
            "border_bgr": (240, 240, 240),
            "solid": True,
            "bold": False,
            "align": "left",
            "contrast": 223.0,
        }

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    # 内缩采样，避开 OCR 框蹭到的括号线/色带边缘
    pad = 2 if min(h, w) > 10 else 0
    y0, y1b, x0, x1b = pad, h - pad, pad, w - pad
    if y1b <= y0 + 2 or x1b <= x0 + 2:
        y0, y1b, x0, x1b = 0, h, 0, w
    band = max(1, min(2, (y1b - y0) // 4, (x1b - x0) // 4))
    border = np.concatenate(
        [
            roi[y0 : y0 + band, x0:x1b, :].reshape(-1, 3),
            roi[y1b - band : y1b, x0:x1b, :].reshape(-1, 3),
            roi[y0:y1b, x0 : x0 + band, :].reshape(-1, 3),
            roi[y0:y1b, x1b - band : x1b, :].reshape(-1, 3),
        ]
    )
    border_f = border.astype(np.float32)
    border_bgr = _median_bgr(border)
    # 按通道：先取贴近中位数的内点再算 std，避免少数蹭线像素抬高 std
    med = np.array(border_bgr, dtype=np.float32)
    deltas = np.abs(border_f - med).max(axis=1)
    inliers = border_f[deltas <= 18]
    frac = float(len(inliers) / max(1, len(border_f)))
    if len(inliers) >= 8:
        chan_std = float(np.std(inliers, axis=0).max())
    else:
        chan_std = float(np.std(border_f, axis=0).max())
    solid = chan_std < SOLID_STD_MAX and frac >= SOLID_FRAC_MIN

    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask_hi = th > 0
    mask_lo = ~mask_hi
    n_hi, n_lo = int(mask_hi.sum()), int(mask_lo.sum())
    if n_hi == 0 and n_lo == 0:
        text_mask = np.zeros_like(gray, dtype=bool)
        bg_mask = np.ones_like(gray, dtype=bool)
    elif n_hi <= n_lo:
        text_mask, bg_mask = mask_hi, mask_lo
    else:
        text_mask, bg_mask = mask_lo, mask_hi

    # 纯色：边框中位数抗文字污染；非纯色：Otsu 背景类
    if solid:
        bg_bgr = border_bgr
    else:
        bg_bgr = _median_bgr(roi[bg_mask]) if bg_mask.any() else border_bgr
    fg_bgr = _median_bgr(roi[text_mask]) if text_mask.any() else (17, 17, 17)

    contrast = abs(_gray_of(fg_bgr) - _gray_of(bg_bgr))
    if contrast < CONTRAST_MIN:
        fg_bgr = (255, 255, 255) if _gray_of(bg_bgr) < 140 else (0, 0, 0)
        contrast = abs(_gray_of(fg_bgr) - _gray_of(bg_bgr))

    area_ratio = float(text_mask.sum()) / float(max(1, h * w))
    bold = area_ratio >= BOLD_AREA_RATIO

    # 对齐从行间一致性推断，禁止质心对框中心三分桶（密排图几乎全判 center）
    geom = _ink_geometry(roi)
    solid_colored = solid and not _is_near_white(_quantize_bgr(bg_bgr))
    align = _infer_align(geom.get("rows") or [], solid=solid_colored)

    return {
        "bg_bgr": bg_bgr,
        "fg_bgr": fg_bgr,
        "border_bgr": border_bgr,
        "solid": solid,
        "solid_colored": solid_colored,
        "bold": bold,
        "align": align,
        "contrast": contrast,
    }


def _ink_geometry(roi: np.ndarray) -> dict:
    """原文墨迹几何：整体 ink bbox + 按 y 投影空行切出的每行 x1/cx/x2。

    坐标相对 ROI 左上角。排版锚点必须用这套几何，禁止用可用区中心。
    """
    tm = _text_mask_u8(roi)
    if tm.size == 0:
        return {
            "ink_x1": 0,
            "ink_y1": 0,
            "ink_x2": 0,
            "ink_y2": 0,
            "ink_cx": 0.0,
            "ink_cy": 0.0,
            "rows": [],
        }
    h, w = tm.shape[:2]
    mask = tm > 0
    if not mask.any():
        return {
            "ink_x1": 0,
            "ink_y1": 0,
            "ink_x2": max(0, w - 1),
            "ink_y2": max(0, h - 1),
            "ink_cx": w / 2.0,
            "ink_cy": h / 2.0,
            "rows": [],
        }
    ys, xs = np.where(mask)
    ink_x1, ink_x2 = int(xs.min()), int(xs.max())
    ink_y1, ink_y2 = int(ys.min()), int(ys.max())
    rows: list[dict] = []
    y_proj = mask.any(axis=1)
    in_run = False
    start = 0
    for y in range(h):
        if y_proj[y] and not in_run:
            in_run = True
            start = y
        elif (not y_proj[y]) and in_run:
            in_run = False
            band = mask[start:y, :]
            if band.any():
                rxs = np.where(band.any(axis=0))[0]
                rys = np.where(band.any(axis=1))[0]
                rx1, rx2 = int(rxs.min()), int(rxs.max())
                rows.append(
                    {
                        "x1": rx1,
                        "x2": rx2,
                        "cx": (rx1 + rx2) / 2.0,
                        "y1": start + int(rys.min()),
                        "y2": start + int(rys.max()),
                    }
                )
    if in_run:
        band = mask[start:h, :]
        if band.any():
            rxs = np.where(band.any(axis=0))[0]
            rys = np.where(band.any(axis=1))[0]
            rx1, rx2 = int(rxs.min()), int(rxs.max())
            rows.append(
                {
                    "x1": rx1,
                    "x2": rx2,
                    "cx": (rx1 + rx2) / 2.0,
                    "y1": start + int(rys.min()),
                    "y2": start + int(rys.max()),
                }
            )
    return {
        "ink_x1": ink_x1,
        "ink_y1": ink_y1,
        "ink_x2": ink_x2,
        "ink_y2": ink_y2,
        "ink_cx": (ink_x1 + ink_x2) / 2.0,
        "ink_cy": (ink_y1 + ink_y2) / 2.0,
        "rows": rows,
    }


def _is_rule_row(row: dict, h_max: int) -> bool:
    """线状行：宽高比超阈值且高度不足最高行比例（括号线/色带）。"""
    h = max(1, int(row["y2"]) - int(row["y1"]))
    w = max(1, int(row["x2"]) - int(row["x1"]))
    return w / h >= RULE_ROW_RATIO and h < h_max * RULE_ROW_H_FRAC


def _text_rows(rows: list[dict]) -> list[dict]:
    """排除线状行后的文字行；若全是线状行则回退全部行。"""
    if not rows:
        return []
    heights = [max(1, int(r["y2"]) - int(r["y1"])) for r in rows]
    h_max = max(heights)
    texty = [r for r in rows if not _is_rule_row(r, h_max)]
    return texty or list(rows)


def _main_row(rows: list[dict]) -> dict | None:
    """锚点行：排除线状行（括号线/色带）后取最宽的一行。

    OCR 框常蹭到贯穿全宽的细线，若按「最宽」直接选行会锚到那条线上。
    """
    pool = _text_rows(rows)
    if not pool:
        return None
    return max(pool, key=lambda r: int(r["x2"]) - int(r["x1"]))


def _fill_band(roi: np.ndarray, *, pad: int = FILL_BAND_PAD) -> tuple[int, int]:
    """实心填充纵向范围：非线状文字行 y 包络 ±pad；无文字行回退整框。

    相对 ROI 顶部。OCR 框常比文字带宽，整框填充会抹掉框边缘的括号线。
    """
    h = int(roi.shape[0]) if roi.size else 0
    if h <= 0:
        return 0, 0
    rows = (_ink_geometry(roi).get("rows") or [])
    if not rows:
        return 0, h
    heights = [max(1, int(r["y2"]) - int(r["y1"])) for r in rows]
    h_max = max(heights)
    texty = [r for r in rows if not _is_rule_row(r, h_max)]
    if not texty:
        return 0, h
    y1 = max(0, min(int(r["y1"]) for r in texty) - pad)
    y2 = min(h, max(int(r["y2"]) for r in texty) + 1 + pad)
    if y2 <= y1:
        return 0, h
    return y1, y2


def _line_guard_mask(
    roi: np.ndarray, bg_bgr: tuple[int, int, int], tm: np.ndarray | None = None
) -> np.ndarray:
    """贯穿性线条/色带保护掩膜（uint8 0/255）。

    对「非背景且非文字」像素做 1×K / K×1 开运算，存活者即长线图元。
    挡住填充/inpaint 抹掉穿过文字带的竖线或箭头杆。
    """
    if roi.size == 0:
        return np.zeros((0, 0), np.uint8)
    h, w = roi.shape[:2]
    if tm is None:
        tm = _text_mask_u8(roi)
    text = tm > 0 if tm.size else np.zeros((h, w), bool)
    bg = np.array(bg_bgr, dtype=np.int16)
    diff = np.abs(roi.astype(np.int16) - bg).max(axis=2)
    candidate = (diff > 40) & (~text)
    u8 = (candidate.astype(np.uint8) * 255)
    kx = max(3, int(round(w * LINE_GUARD_FRAC)))
    ky = max(3, int(round(h * LINE_GUARD_FRAC)))
    if kx % 2 == 0:
        kx += 1
    if ky % 2 == 0:
        ky += 1
    # 含文字 mask 的长横线（括号顶边常被 Otsu 标成字，排除后线保护为 0）
    all_ink = ((diff > 40).astype(np.uint8) * 255)
    horiz_ink = cv2.morphologyEx(all_ink, cv2.MORPH_OPEN, np.ones((1, kx), np.uint8))
    if not u8.any():
        return horiz_ink
    horiz = cv2.morphologyEx(u8, cv2.MORPH_OPEN, np.ones((1, kx), np.uint8))
    vert = cv2.morphologyEx(u8, cv2.MORPH_OPEN, np.ones((ky, 1), np.uint8))
    return np.maximum(np.maximum(horiz, vert), horiz_ink)


def _infer_align(rows: list[dict], *, solid: bool = False) -> str:
    """多行比各行 x1/cx/x2 标准差，最小者即原文对齐；单行/实心色块取 center。"""
    # 实心「彩色」块上的标签在设计上几乎总是居中（流程图蓝框等）；
    # 白底 solid 只是底色干净，不代表居中，须走正常推断
    if solid:
        return "center"
    if len(rows) < 2:
        return "center"
    x1s = [float(r["x1"]) for r in rows]
    cxs = [float(r["cx"]) for r in rows]
    x2s = [float(r["x2"]) for r in rows]
    stds = {
        "left": float(np.std(x1s)),
        "center": float(np.std(cxs)),
        "right": float(np.std(x2s)),
    }
    best = min(stds, key=stds.get)  # type: ignore[arg-type]
    # 标准差接近时偏向 center，避免长短行把居中误判成右/左对齐
    if best != "center" and stds[best] >= stds["center"] * 0.85:
        return "center"
    return best


def _text_mask_u8(
    roi: np.ndarray, *, heavy: bool = False
) -> np.ndarray:
    """Otsu 少数类作文字 mask（uint8 0/255），轻膨胀覆盖抗锯齿。

    heavy=True（PLAN-027g）：3×3 / 2 次，专打描边残留；线保护须用 light，
    避免括号线被并入文字 mask 后失去 _line_guard 保护。
    """
    if roi.size == 0:
        return np.zeros((0, 0), np.uint8)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask_hi = th > 0
    n_hi, n_lo = int(mask_hi.sum()), int((~mask_hi).sum())
    text = mask_hi if n_hi <= n_lo else ~mask_hi
    u8 = (text.astype(np.uint8) * 255)
    if u8.size:
        if heavy:
            u8 = cv2.dilate(u8, np.ones((3, 3), np.uint8), iterations=2)
        else:
            u8 = cv2.dilate(u8, np.ones((2, 2), np.uint8), iterations=1)
    return u8


def _expand_erase_rect(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    img_h: int,
    img_w: int,
    pad: int | None = None,
) -> tuple[int, int, int, int]:
    """擦除前扩框，夹在图像边界内。"""
    p = int(ERASE_PAD_PX if pad is None else pad)
    return (
        max(0, x1 - p),
        max(0, y1 - p),
        min(img_w, x2 + p),
        min(img_h, y2 + p),
    )


def _clear_ocr_leftovers(
    img_cv: np.ndarray,
    boxes: list,
    styles: list[dict],
    redraw: list[bool],
    *,
    orig_texts: list[str] | None = None,
) -> int:
    """擦除后二次 OCR：仍检出原文类墨迹则只擦原框内文字像素。返回清理框数。

    上限一轮。扩框只用于检出抗锯齿环上的残字；落笔仍限原 OCR 框，避免抹括号线。
    """
    import tempfile

    cleared = 0
    img_h, img_w = img_cv.shape[:2]
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        ox1, oy1, ox2, oy2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        x1, y1, x2, y2 = _expand_erase_rect(
            ox1, oy1, ox2, oy2, img_h=img_h, img_w=img_w
        )
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        roi = img_cv[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        bg = tuple(int(c) for c in styles[i].get("bg_bgr", (255, 255, 255)))
        leftover_need = int(
            (np.abs(roi.astype(np.int16) - np.array(bg, dtype=np.int16)).max(axis=2) > 40).sum()
        )
        if leftover_need < 12:
            continue
        leftover = []
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
                cv2.imwrite(tmp_path, roi)
            leftover = ocr_image_rapid(tmp_path)
        except Exception as exc:
            logger.debug("leftover OCR failed box %s: %s", i, exc)
            leftover = []
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        if not leftover:
            continue
        src_hint = ""
        if orig_texts and i < len(orig_texts):
            src_hint = (orig_texts[i] or "").strip().lower()
        need = False
        for lb in leftover:
            t = (lb[4] or "").strip()
            if not t:
                continue
            tl = t.lower()
            if src_hint and (tl in src_hint or src_hint in tl):
                need = True
                break
            if any(ch.isalpha() or ("\u4e00" <= ch <= "\u9fff") for ch in t):
                need = True
                break
        if not need:
            continue
        # 只在原 OCR 框内擦文字像素（heavy mask，线保护用 light）
        roi0 = img_cv[oy1:oy2, ox1:ox2]
        tm = _text_mask_u8(roi0, heavy=True)
        g = _line_guard_mask(roi0, bg, _text_mask_u8(roi0, heavy=False))
        if tm.size and int(tm.max()) > 0:
            m = tm > 0
            if g.size and int(g.max()) > 0:
                m = m & (g == 0)
            img_cv[oy1:oy2, ox1:ox2][m] = bg
            cleared += 1
    return cleared


def _erase_text_local(img: np.ndarray, x1: int, y1: int, x2: int, y2: int, tm: np.ndarray) -> None:
    """非纯色：文字像素用邻域非文字中位数替换，保留色带/括号线。"""
    if tm.size == 0 or not (tm > 0).any():
        return
    roi = img[y1:y2, x1:x2]
    h, w = roi.shape[:2]
    text = tm > 0
    bg_mask = ~text
    if not bg_mask.any():
        return
    # 全局回退色
    fallback = _median_bgr(roi[bg_mask])
    ys, xs = np.where(text)
    out = roi.copy()
    for yy, xx in zip(ys, xs):
        y0, y1b = max(0, yy - 3), min(h, yy + 4)
        x0, x1b = max(0, xx - 3), min(w, xx + 4)
        patch = roi[y0:y1b, x0:x1b]
        local_bg = bg_mask[y0:y1b, x0:x1b]
        if local_bg.any():
            out[yy, xx] = _median_bgr(patch[local_bg])
        else:
            out[yy, xx] = fallback
    img[y1:y2, x1:x2] = out


def _bgr_to_rgb(bgr: tuple[int, int, int]) -> tuple[int, int, int]:
    return (bgr[2], bgr[1], bgr[0])


def _text_size(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return font.getsize(text)  # type: ignore[attr-defined]


def _ink_x_metrics(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    """真实墨迹水平范围 (左边距, 墨迹宽)。

    `font.getbbox()` 返回布局盒（x0 恒 0、x2 为步进宽），拿不到左边距；
    「·」或前导空格会让文字整体右移。`getmask().getbbox()` 才是实际墨迹。
    """
    try:
        mask = font.getmask(text)
        bb = mask.getbbox()
        if bb:
            return int(bb[0]), max(1, int(bb[2]) - int(bb[0]))
    except (AttributeError, OSError, ValueError):
        pass
    return 0, _text_size(font, text)[0]


def _line_height(font: ImageFont.ImageFont, size_hint: int = 0) -> int:
    """真实行高：ascent+descent，禁止用 getbbox 墨迹高判能否放下。"""
    if hasattr(font, "getmetrics"):
        ascent, descent = font.getmetrics()
        return int(ascent + descent)
    if size_hint > 0:
        return int(size_hint * 1.2)
    return max(12, _text_size(font, "Ag")[1])


def _wrap_text(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    """按词/字换行，使每行宽度不超过 max_w。"""
    if max_w <= 0:
        return [text]
    if any(ord(c) > 127 for c in text):
        tokens = list(text)
        joiner = ""
    else:
        tokens = text.split(" ")
        joiner = " "

    lines: list[str] = []
    cur = ""
    for tok in tokens:
        candidate = tok if not cur else (cur + joiner + tok)
        w, _ = _text_size(font, candidate)
        if w <= max_w or not cur:
            cur = candidate
        else:
            lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines or [text]


def _fit_font_and_lines(
    text: str,
    box_w: int,
    box_h: int,
    font_path: str | None,
    max_size: int,
    min_size: int = 10,
) -> tuple[ImageFont.ImageFont, list[str], int, int]:
    """二分字号：优先单行，放不下则换行；返回 (font, lines, size, line_h)。"""
    lo, hi = min_size, max(min_size, max_size)
    best_font = ImageFont.load_default()
    best_lines = [text]
    best_size = min_size
    best_lh = _line_height(best_font, best_size)

    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid) if font_path else ImageFont.load_default()
        lh = _line_height(font, mid)
        tw, _ = _text_size(font, text)
        if tw <= box_w and lh <= box_h:
            best_font, best_lines, best_size, best_lh = font, [text], mid, lh
            lo = mid + 1
            continue
        lines = _wrap_text(text, font, max(8, box_w))
        if not lines:
            hi = mid - 1
            continue
        total_h = lh * len(lines) + max(0, len(lines) - 1) * max(1, mid // 8)
        max_line_w = max((_text_size(font, ln)[0] for ln in lines), default=tw)
        if max_line_w <= box_w * 1.05 and total_h <= box_h:
            best_font, best_lines, best_size, best_lh = font, lines, mid, lh
            lo = mid + 1
        else:
            hi = mid - 1

    if best_size == min_size and font_path:
        best_font = ImageFont.truetype(font_path, min_size)
        best_lh = _line_height(best_font, min_size)
        best_lines = _wrap_text(text, best_font, max(8, box_w))
    return best_font, best_lines, best_size, best_lh


def _rects_overlap(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _available_box(
    box: tuple[int, int, int, int],
    all_boxes: list[tuple[int, int, int, int]],
    img: np.ndarray,
    bg_bgr: tuple[int, int, int],
) -> tuple[int, int, int, int]:
    """从 OCR 框向外扩到碰邻框或非背景像素为止；擦除仍用原框，排版用本框。"""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    ow, oh = max(1, x2 - x1), max(1, y2 - y1)
    max_w = int(ow * AVAIL_W_MULT)
    max_h = int(oh * AVAIL_H_MULT)
    bg = np.array(bg_bgr, dtype=np.float32)

    others = [b for b in all_boxes if b != box]

    def hits_other(r: tuple[int, int, int, int]) -> bool:
        return any(_rects_overlap(r, o) for o in others)

    def col_ok(x: int, ya: int, yb: int) -> bool:
        if x < 0 or x >= w:
            return False
        strip = img[ya:yb, x : x + 1].reshape(-1, 3).astype(np.float32)
        if strip.size == 0:
            return False
        return float(np.abs(strip - bg).max(axis=1).mean()) <= AVAIL_BG_DELTA

    def row_ok(y: int, xa: int, xb: int) -> bool:
        if y < 0 or y >= h:
            return False
        strip = img[y : y + 1, xa:xb].reshape(-1, 3).astype(np.float32)
        if strip.size == 0:
            return False
        return float(np.abs(strip - bg).max(axis=1).mean()) <= AVAIL_BG_DELTA

    # 向右
    while (x2 - x1) < max_w and x2 < w:
        cand = (x1, y1, x2 + 1, y2)
        if hits_other(cand) or not col_ok(x2, y1, y2):
            break
        x2 += 1
    # 向左
    while (x2 - x1) < max_w and x1 > 0:
        cand = (x1 - 1, y1, x2, y2)
        if hits_other(cand) or not col_ok(x1 - 1, y1, y2):
            break
        x1 -= 1
    # 向下
    while (y2 - y1) < max_h and y2 < h:
        cand = (x1, y1, x2, y2 + 1)
        if hits_other(cand) or not row_ok(y2, x1, x2):
            break
        y2 += 1
    # 向上
    while (y2 - y1) < max_h and y1 > 0:
        cand = (x1, y1 - 1, x2, y2)
        if hits_other(cand) or not row_ok(y1 - 1, x1, x2):
            break
        y1 -= 1

    return (x1, y1, x2, y2)


def _quantize_bgr(bgr: tuple[int, int, int], step: int = TIER_BG_STEP) -> tuple[int, int, int]:
    return tuple(min(255, int(round(c / step) * step)) for c in bgr)


def _is_near_white(bgr: tuple[int, int, int]) -> bool:
    return sum(bgr) >= 720


def _ink_height(roi: np.ndarray) -> int:
    """ROI 内文字墨迹垂直高度（Otsu 少数类）。"""
    if roi.size == 0:
        return 0
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = th > 0
    if int(mask.sum()) > int((~mask).sum()):
        mask = ~mask
    ys = np.where(mask.any(axis=1))[0]
    if len(ys) == 0:
        return 0
    return int(ys.max() - ys.min() + 1)


def _estimate_orig_size(
    text: str, ink_h: int, font_path: str | None, bold: bool = False
) -> int:
    """反推原图标称字号：同一原文渲染墨迹高不超过实测值的最大字号。"""
    if ink_h <= 0 or not text:
        return max(12, ink_h)
    path = font_path
    lo, hi, best = 8, max(8, min(140, ink_h * 3)), 8
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            font = ImageFont.truetype(path, mid) if path else ImageFont.load_default()
        except OSError:
            font = ImageFont.load_default()
        rendered = _text_size(font, text)[1]
        if rendered <= ink_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _assign_left_groups(
    boxes: list,
    styles: list[dict],
    redraw: list[bool],
    orig: np.ndarray,
) -> dict[int, float]:
    """跨框左对齐组：纵向邻接且原文左墨迹边一致的框（项目符号列表/条目块）。

    单行框各自看都是「居中」，只有放在一起才看得出是左对齐；译文长短不一时
    逐框居中会让 bullet 参差。返回 {box_index: 共同左锚 x}。
    """
    items: list[dict] = []
    for i, b in enumerate(boxes):
        if not redraw[i] or styles[i].get("solid_colored"):
            continue
        ox1, oy1, ox2, oy2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        row = _main_row((_ink_geometry(orig[oy1:oy2, ox1:ox2]).get("rows") or []))
        if not row:
            continue
        items.append(
            {
                "i": i,
                "x1": ox1 + float(row["x1"]),
                "x2": ox1 + float(row["x2"]),
                "y1": oy1,
                "y2": oy2,
                "h": max(1, oy2 - oy1),
            }
        )
    items.sort(key=lambda t: t["y1"])

    out: dict[int, float] = {}
    used = [False] * len(items)
    for a in range(len(items)):
        if used[a]:
            continue
        group = [items[a]]
        used[a] = True
        for b_i in range(a + 1, len(items)):
            if used[b_i]:
                continue
            prev, cur = group[-1], items[b_i]
            if abs(cur["x1"] - prev["x1"]) > LEFT_GROUP_TOL_PX:
                continue
            if cur["y1"] - prev["y2"] > prev["h"] * LEFT_GROUP_GAP_MULT:
                continue
            group.append(cur)
            used[b_i] = True
        if len(group) < 2:
            continue
        # 等宽条目（刻度标签之类）左/中/右无从区分，居中更稳；
        # 只有右端明显参差才构成「左对齐」的证据
        x2s = [g["x2"] for g in group]
        if max(x2s) - min(x2s) < LEFT_GROUP_TOL_PX * 3:
            continue
        anchor = float(np.median([g["x1"] for g in group]))
        for g in group:
            out[g["i"]] = anchor
    return out


def _assign_tiers(
    boxes: list, styles: list[dict]
) -> list[str]:
    """背景色桶 + 白底 y 行带 → 每框 tier key。"""
    n = len(boxes)
    keys: list[str] = [""] * n
    white_idx: list[int] = []
    for i, (b, st) in enumerate(zip(boxes, styles)):
        q = _quantize_bgr(st["bg_bgr"])
        if _is_near_white(q):
            white_idx.append(i)
        else:
            keys[i] = f"c{q[0]}_{q[1]}_{q[2]}"

    if not white_idx:
        return keys

    white_idx.sort(key=lambda i: (boxes[i][1] + boxes[i][3]) // 2)
    heights = [max(1, boxes[i][3] - boxes[i][1]) for i in white_idx]
    med_h = float(np.median(heights)) if heights else 40.0
    thr = max(1.5 * med_h, 80.0)
    band = 0
    keys[white_idx[0]] = f"w{band}"
    for a, b in zip(white_idx, white_idx[1:]):
        cy_a = (boxes[a][1] + boxes[a][3]) // 2
        cy_b = (boxes[b][1] + boxes[b][3]) // 2
        if cy_b - cy_a > thr:
            band += 1
        keys[b] = f"w{band}"
    return keys


def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    arr = sorted(vals)
    if len(arr) == 1:
        return float(arr[0])
    k = (len(arr) - 1) * p
    f = int(k)
    c = min(f + 1, len(arr) - 1)
    if f == c:
        return float(arr[f])
    return float(arr[f] + (arr[c] - arr[f]) * (k - f))


def _assign_tier_sizes(
    *,
    boxes: list,
    texts: list[str],
    finals: list[str],
    redraw: list[bool],
    styles: list[dict],
    avails: list[tuple[int, int, int, int]],
    orig: np.ndarray,
    font_regular: str | None,
    font_bold: str | None,
) -> dict:
    """层级归一：原图 75 分位字号 + 全局比例 k + outlier 降级。"""
    tiers = _assign_tiers(boxes, styles)
    n = len(boxes)
    est_sizes = [0] * n
    fit_sizes = [0] * n
    bold_flags = [bool(styles[i].get("bold")) for i in range(n)]

    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        roi = orig[max(0, y1):y2, max(0, x1):x2]
        ink = _ink_height(roi)
        use = font_bold if bold_flags[i] and font_bold else font_regular
        est_sizes[i] = _estimate_orig_size(texts[i], ink, use, bold_flags[i])

    # 组 orig_em（75 分位）+ 粗细多数决
    by_tier: dict[str, list[int]] = {}
    for i in range(n):
        if redraw[i]:
            by_tier.setdefault(tiers[i], []).append(i)

    orig_em: dict[str, int] = {}
    tier_bold: dict[str, bool] = {}
    for t, idxs in by_tier.items():
        ests = [est_sizes[i] for i in idxs if est_sizes[i] > 0]
        orig_em[t] = max(10, int(round(_percentile(ests, 0.75)))) if ests else 24
        # 033k：禁止层级多数投票；粗体由块级 source_style 继承
        tier_bold[t] = False

    # 每框最大可行字号（用组粗细）
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        ax1, ay1, ax2, ay2 = avails[i]
        box_w = max(8, ax2 - ax1)
        box_h = max(8, ay2 - ay1)
        max_size = max(12, min(int(box_h * 0.9), 72))
        use = font_bold if tier_bold.get(tiers[i]) and font_bold else font_regular
        _, _, fit, _ = _fit_font_and_lines(finals[i], box_w, box_h, use, max_size)
        fit_sizes[i] = fit

    # 比值与 outlier
    ratios: dict[str, list[float]] = {t: [] for t in by_tier}
    for i in range(n):
        if not redraw[i]:
            continue
        em = max(1, orig_em[tiers[i]])
        ratios[tiers[i]].append(fit_sizes[i] / em)

    outliers: set[int] = set()
    for t, idxs in by_tier.items():
        rs = ratios.get(t) or []
        if not rs:
            continue
        med = float(np.median(rs))
        for i in idxs:
            em = max(1, orig_em[t])
            r = fit_sizes[i] / em
            if med > 0 and r < TIER_OUTLIER_RATIO * med:
                outliers.add(i)

    # 全局 k
    k_vals = []
    for i in range(n):
        if not redraw[i] or i in outliers:
            continue
        em = max(1, orig_em[tiers[i]])
        k_vals.append(fit_sizes[i] / em)
    k = min(k_vals) if k_vals else 1.0
    k = max(0.15, min(1.0, k))

    assigned = [0] * n
    tier_size: dict[str, int] = {}
    for t, em in orig_em.items():
        tier_size[t] = max(10, int(round(k * em)))

    for i in range(n):
        if not redraw[i]:
            continue
        if i in outliers:
            assigned[i] = fit_sizes[i]
        else:
            assigned[i] = tier_size[tiers[i]]

    return {
        "tiers": tiers,
        "assigned": assigned,
        "fit_sizes": fit_sizes,
        "est_sizes": est_sizes,
        "orig_em": orig_em,
        "tier_size": tier_size,
        "tier_bold": tier_bold,
        "outliers": sorted(i + 1 for i in outliers),
        "k": k,
    }


def _padded_draw_window(
    db: dict | None, iw: int, ih: int, *, pad: int = 4
) -> tuple[int, int, int, int] | None:
    """C3/C8 共用：计划绘制盒外扩 pad，钳在图像内。"""
    if not isinstance(db, dict):
        return None
    try:
        x1 = max(0, int(db["x1"]) - pad)
        y1 = max(0, int(db["y1"]) - pad)
        x2 = min(iw, int(db["x2"]) + pad)
        y2 = min(ih, int(db["y2"]) + pad)
    except (KeyError, TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _c3_window(
    box,
    avail: tuple[int, int, int, int],
    planned: dict | None,
    iw: int,
    ih: int,
) -> tuple[tuple[int, int, int, int], bool]:
    db = planned.get("draw_bbox") if isinstance(planned, dict) else None
    win = _padded_draw_window(db, iw, ih)
    if win is not None:
        return win, True
    x1, y1, x2, y2 = avail
    ox1, oy1, ox2, oy2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    return (
        (
            max(0, min(x1, ox1)),
            max(0, min(y1, oy1)),
            min(iw, max(x2, ox2)),
            min(ih, max(y2, oy2)),
        ),
        False,
    )


def _c3_is_blank(diff: np.ndarray, used_draw_bbox: bool) -> bool:
    if diff.size == 0:
        return True
    ratio = float(diff.mean())
    ink_px = int(diff.sum())
    if used_draw_bbox:
        return ratio < QC_INK_MIN
    return ink_px < QC_INK_MIN_PX


def _qc_report(
    *,
    out_path: Path,
    boxes: list,
    texts: list[str],
    trans: dict[int, str],
    redraw: list[bool],
    drawn: int,
    styles: list[dict],
    avails: list[tuple[int, int, int, int]],
    sizes: list[int],
    line_heights: list[int],
    line_lists: list[list[str]],
    fonts: list,
    erased_bgr: np.ndarray,
    final_rgb: np.ndarray,
    tier_meta: dict | None = None,
    orig_bgr: np.ndarray | None = None,
    anchors: list[dict | None] | None = None,
) -> dict:
    """QC：覆盖/绘制/墨迹/对比度/溢出/可读性 + 层级一致与比例 + 对齐。"""
    issues: list[dict] = []
    warnings: list[dict] = []

    # C1 覆盖
    missing = [i + 1 for i in range(len(boxes)) if not (trans.get(i + 1) or "").strip()]
    if missing:
        issues.append(
            {
                "code": "C1",
                "msg": f"untranslated boxes={missing}",
                "samples": [texts[i - 1][:40] for i in missing[:8]],
            }
        )

    # C2 绘制
    expect = sum(1 for r in redraw if r)
    if drawn != expect:
        issues.append({"code": "C2", "msg": f"drawn={drawn} expect={expect}"})

    # C3 墨迹实测：优先 draw_bbox 小窗（与 C8 同口径）；无计划盒才回退 avail∪ocr，
    # 且用绝对墨迹像素下限，避免流程图短标签在大白盒里被比例误判空白。
    final_bgr = cv2.cvtColor(final_rgb, cv2.COLOR_RGB2BGR)
    ih, iw = final_bgr.shape[:2]
    blanks: list[int] = []
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        planned = (anchors[i] if anchors and i < len(anchors) else None) or {}
        (x1, y1, x2, y2), used_draw = _c3_window(b, avails[i], planned, iw, ih)
        a = erased_bgr[y1:y2, x1:x2]
        c = final_bgr[y1:y2, x1:x2]
        if a.size == 0 or c.size == 0:
            blanks.append(i + 1)
            continue
        diff = np.abs(a.astype(np.int16) - c.astype(np.int16)).max(axis=2) > 8
        if _c3_is_blank(diff, used_draw):
            blanks.append(i + 1)
    if blanks:
        issues.append({"code": "C3", "msg": f"blank boxes={blanks}"})

    # C4 对比度
    low_c = [
        i + 1
        for i, st in enumerate(styles)
        if redraw[i] and float(st.get("contrast", 0)) < CONTRAST_MIN
    ]
    if low_c:
        issues.append({"code": "C4", "msg": f"low contrast boxes={low_c}"})

    # C5 溢出
    overflows: list[int] = []
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        ax1, ay1, ax2, ay2 = avails[i]
        aw, ah = max(1, ax2 - ax1), max(1, ay2 - ay1)
        lines = line_lists[i]
        font = fonts[i]
        lh = line_heights[i]
        gap = max(1, sizes[i] // 8)
        total_h = lh * len(lines) + gap * max(0, len(lines) - 1)
        max_tw = max((_text_size(font, ln)[0] for ln in lines), default=0)
        if max_tw > aw + 1 or total_h > ah + 1:
            overflows.append(i + 1)
    if overflows:
        issues.append({"code": "C5", "msg": f"overflow boxes={overflows}"})

    # C6 可读性（WARN）
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        oh = max(1, b[3] - b[1])
        if sizes[i] < 0.6 * oh:
            warnings.append(
                {
                    "code": "C6",
                    "box": i + 1,
                    "msg": f"size={sizes[i]} < 0.6*ocr_h={oh}",
                    "text": (trans.get(i + 1) or "")[:40],
                }
            )

    tiers_info: dict = {}
    if tier_meta:
        tiers = tier_meta.get("tiers") or []
        orig_em = tier_meta.get("orig_em") or {}
        tier_size = tier_meta.get("tier_size") or {}
        outliers = set(tier_meta.get("outliers") or [])
        k = float(tier_meta.get("k") or 1.0)
        by_tier: dict[str, list[int]] = {}
        for i, t in enumerate(tiers):
            if redraw[i]:
                by_tier.setdefault(t, []).append(i)

        # C7a 组内一致
        inconsistent = []
        for t, idxs in by_tier.items():
            members = [i for i in idxs if (i + 1) not in outliers]
            if len(members) < 2:
                continue
            s0 = sizes[members[0]]
            if any(sizes[i] != s0 for i in members[1:]):
                inconsistent.append(t)
        if inconsistent:
            issues.append({"code": "C7a", "msg": f"tier size mismatch={inconsistent}"})

        # C7b 组间比例
        ratio_bad = []
        for t, em in orig_em.items():
            if em <= 0 or t not in tier_size:
                continue
            r = tier_size[t] / em
            if abs(r - k) > TIER_RATIO_TOL * max(k, 1e-6) + 1e-6:
                # 允许 ±1px 取整误差
                expected = max(10, int(round(k * em)))
                if tier_size[t] != expected:
                    ratio_bad.append({"tier": t, "ratio": round(r, 4), "k": round(k, 4)})
        if ratio_bad:
            issues.append({"code": "C7b", "msg": "tier ratio drift", "detail": ratio_bad})

        for t, idxs in by_tier.items():
            tiers_info[t] = {
                "orig_em": orig_em.get(t),
                "size": tier_size.get(t),
                "n": len(idxs),
                "members": [i + 1 for i in idxs],
            }
        for ob in outliers:
            warnings.append(
                {
                    "code": "C7o",
                    "box": ob,
                    "msg": "tier outlier; used private fit size",
                }
            )

    # C8 对齐：成品墨迹 vs 计划绘制锚点（draw_bbox），验证「画到了该画的位置」。
    # 相对原文的漂移在 planned.shift / ink_src 里可审计；图像边界 clamp 不算 C8 失败。
    align_details: list[dict] = []
    misaligned: list[dict] = []
    if orig_bgr is not None:
        ih, iw = final_bgr.shape[:2]
        for i, b in enumerate(boxes):
            if not redraw[i]:
                continue
            ox1, oy1, ox2, oy2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            planned = (anchors[i] if anchors and i < len(anchors) else None) or {}
            db = planned.get("draw_bbox") if isinstance(planned, dict) else None
            win = _padded_draw_window(db, iw, ih)
            if win is None:
                continue
            mx1, my1, mx2, my2 = win
            dst_roi = final_bgr[my1:my2, mx1:mx2]
            dst_g = _ink_geometry(dst_roi)
            st = styles[i]
            # 用实际生效的锚定模式（左对齐组会覆盖逐框推断）
            align = planned.get("align") or st.get("align") or "center"
            vertical_mode = planned.get("vertical_mode")
            if vertical_mode is None:
                vertical_mode = (
                    "center"
                    if planned.get("solid_colored", st.get("solid_colored"))
                    else "top"
                )
            vertical_center = vertical_mode == "center"
            # 水平 / 竖直锚点口径彼此独立
            if align == "left":
                sx = float(db["x1"])
                dx_abs = mx1 + float(dst_g["ink_x1"])
            elif align == "right":
                sx = float(db["x2"])
                dx_abs = mx1 + float(dst_g["ink_x2"])
            else:
                sx = (int(db["x1"]) + int(db["x2"])) / 2.0
                dx_abs = mx1 + float(dst_g["ink_cx"])
            if vertical_center:
                sy = (int(db["y1"]) + int(db["y2"])) / 2.0
                dy_abs = my1 + float(dst_g["ink_cy"])
            else:
                sy = float(db["y1"])
                dy_abs = my1 + float(dst_g["ink_y1"])
            ddx = dx_abs - sx
            ddy = dy_abs - sy
            ink_src = planned.get("ink_src") or {}
            # 相对原文锚点的位移（审计用）
            if align == "left":
                src_ax = float(ink_src.get("x1") or ox1)
            elif align == "right":
                src_ax = float(ink_src.get("x2") or ox2)
            else:
                src_ax = float(ink_src.get("cx") or ((ox1 + ox2) / 2.0))
            if vertical_center:
                src_ay = float(ink_src.get("cy") or ((oy1 + oy2) / 2.0))
            else:
                src_ay = float(ink_src.get("y1") or oy1)
            plan_dx = sx - src_ax
            plan_dy = sy - src_ay
            entry = {
                "box": i + 1,
                "align": align,
                "vertical_mode": vertical_mode,
                "solid": bool(st.get("solid")),
                "left_group_x": planned.get("left_group_x"),
                "anchor_src": {"x": round(src_ax, 1), "y": round(src_ay, 1)},
                "anchor_plan": {"x": round(sx, 1), "y": round(sy, 1)},
                "anchor_dst": {"x": round(dx_abs, 1), "y": round(dy_abs, 1)},
                "dx": round(ddx, 1),
                "dy": round(ddy, 1),
                "plan_dx": round(plan_dx, 1),
                "plan_dy": round(plan_dy, 1),
                "planned": planned,
            }
            align_details.append(entry)
            if abs(ddx) > ALIGN_TOL_PX or abs(ddy) > ALIGN_TOL_PX:
                misaligned.append(entry)
    if misaligned:
        issues.append(
            {
                "code": "C8",
                "msg": f"align drift boxes={[m['box'] for m in misaligned]}",
                "detail": misaligned[:12],
            }
        )

    # C9 左对齐组：同组成品左墨迹边必须齐（bullet 列表不得参差）
    groups: dict[float, list[dict]] = {}
    for a in align_details:
        gx = a.get("left_group_x")
        if gx is None:
            continue
        groups.setdefault(float(gx), []).append(a)
    ragged = []
    for gx, members in groups.items():
        if len(members) < 2:
            continue
        xs = [float(m["anchor_dst"]["x"]) for m in members]
        spread = max(xs) - min(xs)
        if spread > ALIGN_TOL_PX:
            ragged.append(
                {
                    "group_x": gx,
                    "boxes": [m["box"] for m in members],
                    "spread": round(spread, 1),
                }
            )
    if ragged:
        issues.append({"code": "C9", "msg": "left group ragged", "detail": ragged})

    # C10 图元损伤：OCR 框 − (文字带 ∪ 文字 mask ∪ draw_bbox) 内，
    # 原图非背景却被成品抹成背景。027g 故意擦掉的带外残字计入文字 mask，不算图元损伤。
    graphics_damage: list[dict] = []
    if orig_bgr is not None:
        final_bgr_chk = cv2.cvtColor(final_rgb, cv2.COLOR_RGB2BGR)
        for i, b in enumerate(boxes):
            if not redraw[i]:
                continue
            ox1, oy1, ox2, oy2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            roi_o = orig_bgr[oy1:oy2, ox1:ox2]
            roi_f = final_bgr_chk[oy1:oy2, ox1:ox2]
            if roi_o.size == 0:
                continue
            st = styles[i]
            bg = np.array(st["bg_bgr"], dtype=np.int16)
            by1, by2 = _fill_band(roi_o)
            planned = (anchors[i] if anchors and i < len(anchors) else None) or {}
            db = planned.get("draw_bbox") if isinstance(planned, dict) else None
            protect = np.zeros(roi_o.shape[:2], bool)
            protect[by1:by2, :] = True
            tm_light = _text_mask_u8(roi_o, heavy=False)
            tm = _text_mask_u8(roi_o, heavy=True)
            if tm.size and int(tm.max()) > 0:
                # 贯穿线不算文字：从保护里剔除，仍受 C10 约束
                guard = _line_guard_mask(roi_o, st["bg_bgr"], tm_light)
                text_only = tm > 0
                if guard.size and int(guard.max()) > 0:
                    text_only = text_only & (guard == 0)
                protect |= text_only
            if isinstance(db, dict):
                lx1 = max(0, int(db["x1"]) - ox1)
                ly1 = max(0, int(db["y1"]) - oy1)
                lx2 = min(roi_o.shape[1], int(db["x2"]) - ox1)
                ly2 = min(roi_o.shape[0], int(db["y2"]) - oy1)
                if lx2 > lx1 and ly2 > ly1:
                    protect[ly1:ly2, lx1:lx2] = True
            diff_o = np.abs(roi_o.astype(np.int16) - bg).max(axis=2)
            diff_f = np.abs(roi_f.astype(np.int16) - bg).max(axis=2)
            damaged = (~protect) & (diff_o > 40) & (diff_f <= 15)
            n = int(damaged.sum())
            if n > GRAPHICS_DAMAGE_MAX:
                graphics_damage.append({"box": i + 1, "pixels": n})
    if graphics_damage:
        issues.append(
            {
                "code": "C10",
                "msg": f"graphics damage boxes={[d['box'] for d in graphics_damage]}",
                "detail": graphics_damage[:12],
            }
        )

    from qyunslation.structure.role_fitter import (
        QC_FONT_BELOW_TARGET,
        QC_GRAPHICS_DAMAGE,
        QC_OVERFLOW,
        QC_TRUNCATED,
        QC_UNTRANSLATED,
        QC_WEIGHT_MISMATCH,
    )

    object_qc = []
    for issue in issues:
        code = str(issue.get("code") or "")
        mapped = {
            "C1": QC_UNTRANSLATED,
            "C2": QC_TRUNCATED,
            "C3": QC_TRUNCATED,
            "C5": QC_OVERFLOW,
            "C8": QC_TRUNCATED,
            "C10": QC_GRAPHICS_DAMAGE,
        }.get(code)
        if mapped:
            object_qc.append(mapped)
    if graphics_damage and QC_GRAPHICS_DAMAGE not in object_qc:
        object_qc.append(QC_GRAPHICS_DAMAGE)
    if any("below" in str(w.get("msg", "")).lower() for w in warnings):
        object_qc.append(QC_FONT_BELOW_TARGET)

    report = {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "object_qc": sorted(set(object_qc)),
        "drawn": drawn,
        "boxes": len(boxes),
        "solid_count": sum(1 for st in styles if st.get("solid")),
        "tiers": tiers_info,
        "k": (tier_meta or {}).get("k"),
        "outliers": (tier_meta or {}).get("outliers") or [],
        "align": align_details,
        "align_tol_px": ALIGN_TOL_PX,
        "left_groups": {
            str(gx): [m["box"] for m in members]
            for gx, members in groups.items()
            if len(members) >= 2
        },
        "graphics_damage": graphics_damage,
        "graphics_damage_max": GRAPHICS_DAMAGE_MAX,
    }
    qc_path = Path(str(out_path) + ".qc.json")
    try:
        qc_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("qc json write failed: %s", exc)

    if issues:
        logger.warning("image QC FAIL: %s", json.dumps(issues, ensure_ascii=False))
    if warnings:
        logger.warning("image QC WARN: %s", json.dumps(warnings[:12], ensure_ascii=False))
    if QC_STRICT and issues:
        hard = [
            x
            for x in issues
            if x.get("code") in ("C1", "C2", "C3", "C4", "C8", "C9", "C10")
        ]
        if hard:
            raise RuntimeError(f"image QC strict fail: {hard}")
    return report


def _load_image_bgr_alpha(img_path: Path) -> tuple[np.ndarray, np.ndarray | None, str]:
    """PLAN-027a：加载 BGR 工作图 + 可选 Alpha；保留原模式以便导出。

    OCR/擦除在 RGB/BGR 三通道上进行；输出时把原始 Alpha 贴回。
    """
    with Image.open(img_path) as im:
        mode = im.mode
        has_alpha = mode in ("RGBA", "LA") or (
            mode == "P" and "transparency" in im.info
        )
        alpha = None
        if has_alpha:
            rgba = im.convert("RGBA")
            alpha = np.array(rgba.split()[-1])
            rgb = rgba.convert("RGB")
        else:
            rgb = im.convert("RGB")
        bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        return bgr, alpha, mode


def _save_with_alpha(
    result_rgb: Image.Image,
    out_path: Path,
    alpha: np.ndarray | None,
    *,
    draw_mask: np.ndarray | None = None,
) -> None:
    """保存时恢复 Alpha；译文墨迹处强制不透明。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if alpha is None:
        result_rgb.save(out_path)
        return
    rgba = result_rgb.convert("RGBA")
    arr = np.array(rgba)
    a = alpha.copy()
    if a.shape[:2] != arr.shape[:2]:
        a = cv2.resize(a, (arr.shape[1], arr.shape[0]), interpolation=cv2.INTER_NEAREST)
    if draw_mask is not None and draw_mask.shape[:2] == a.shape[:2]:
        a = np.where(draw_mask > 0, np.uint8(255), a)
    arr[:, :, 3] = a
    Image.fromarray(arr, "RGBA").save(out_path)


def probe_image(
    img_path: str | Path,
    *,
    to_lang: str = "简体中文",
    display_width_pt: float = 0.0,
    display_height_pt: float = 0.0,
    page_frac: float | None = None,
    is_header: bool = False,
) -> dict:
    """PLAN-027a：仅 OCR + 策略判定，不调 LLM。PLAN-027f：透传 ocr_engine。"""
    from qyunslation.extensions.doc_image_policy import evaluate_image_candidate

    img_path = Path(img_path)
    try:
        data = img_path.read_bytes()
    except Exception as exc:
        return {
            "status": "error",
            "should_translate": False,
            "reason": f"read_failed:{exc}",
            "detected_blocks": 0,
            "translatable_blocks": 0,
            "detected_lang": "unknown",
            "text_samples": [],
            "ocr_engine": "none",
        }
    engine = "none"
    try:
        boxes, engine = ocr_image_with_engine(img_path)
    except NotImplementedError as exc:
        return {
            "status": "error",
            "should_translate": False,
            "reason": f"ocr_engine_unimplemented:{exc}",
            "detected_blocks": 0,
            "translatable_blocks": 0,
            "detected_lang": "unknown",
            "text_samples": [],
            "ocr_engine": OCR_ENGINE or "vision",
        }
    except Exception as exc:
        return {
            "status": "error",
            "should_translate": False,
            "reason": f"ocr_failed:{exc}",
            "detected_blocks": 0,
            "translatable_blocks": 0,
            "detected_lang": "unknown",
            "text_samples": [],
            "ocr_engine": engine,
        }
    texts = [b[4] for b in boxes]
    decision = evaluate_image_candidate(
        data,
        display_width_pt=display_width_pt,
        display_height_pt=display_height_pt,
        target_lang=to_lang,
        page_frac=page_frac,
        is_header=is_header,
        ocr_texts=texts,
    )
    samples = [t.strip() for t in texts if t and t.strip()][:8]
    status = "ok" if decision.should_translate else "skip"
    return {
        "status": status,
        "should_translate": decision.should_translate,
        "reason": decision.reason,
        "detected_blocks": decision.detected_blocks or len(texts),
        "translatable_blocks": decision.translatable_blocks,
        "detected_lang": decision.source_lang,
        "text_samples": samples,
        "feature_hash": decision.feature_hash,
        "ocr_engine": engine,
    }


def translate_image(
    img_path: str | Path, out_path: str | Path, to_lang: str = "简体中文"
) -> int:
    """完整图片嵌字翻译。返回实际绘制块数；失败返回 0（调用方应保留原图）。"""
    n, _qc = translate_image_with_qc(img_path, out_path, to_lang=to_lang)
    return n


def translate_image_with_qc(
    img_path: str | Path, out_path: str | Path, to_lang: str = "简体中文"
) -> tuple[int, dict]:
    """完整图片嵌字翻译。返回 (绘制块数, qc_report)。失败返回 (0, {})。"""
    img_path = Path(img_path)
    out_path = Path(out_path)
    if os.environ.get("QYUNSLATION_IMAGE_OVERLAY", "1").lower() in ("0", "false", "off"):
        logger.info("image overlay disabled")
        return 0, {}

    try:
        img_cv, alpha, _mode = _load_image_bgr_alpha(img_path)
    except Exception as exc:
        # 回退 cv2
        logger.warning("PIL load failed, fallback cv2: %s", exc)
        img_cv = cv2.imread(str(img_path))
        alpha = None
    if img_cv is None:
        raise RuntimeError(f"cannot read image: {img_path}")
    orig = img_cv.copy()
    boxes = ocr_image(img_path)
    if not boxes:
        return 0, {}

    texts = [b[4] for b in boxes]
    # PLAN-027a：跳过纯数字/已是目标语种块（不送 LLM，保留原文）
    try:
        from qyunslation.extensions.doc_image_policy import (
            filter_translatable_texts,
            is_numeric_or_unit,
        )

        kept, _lang, skip_all = filter_translatable_texts(texts, target_lang=to_lang)
        if skip_all == "already_target_lang" or (
            skip_all == "no_translatable_text" and not any(
                t.strip() and not is_numeric_or_unit(t) for t in texts
            )
        ):
            return 0, {"ok": True, "skipped": skip_all or "no_translatable_text"}
    except Exception:
        kept = texts

    trans = translate_texts(texts, to_lang=to_lang)

    finals: list[str] = []
    redraw: list[bool] = []
    for i, src in enumerate(texts):
        try:
            from qyunslation.extensions.doc_image_policy import is_numeric_or_unit

            if is_numeric_or_unit(src):
                finals.append(src)
                redraw.append(False)
                continue
        except Exception:
            pass
        zh = (trans.get(i + 1) or "").strip()
        if zh:
            finals.append(zh)
            redraw.append(True)
        else:
            finals.append(src)
            redraw.append(False)

    styles: list[dict] = []
    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        roi = orig[max(0, y1):y2, max(0, x1):x2]
        styles.append(_analyze_box_style(roi))

    ocr_rects = [(b[0], b[1], b[2], b[3]) for b in boxes]
    avails: list[tuple[int, int, int, int]] = []
    for i, b in enumerate(boxes):
        avails.append(
            _available_box(
                (b[0], b[1], b[2], b[3]),
                ocr_rects,
                orig,
                styles[i]["bg_bgr"],
            )
        )

    left_groups = _assign_left_groups(boxes, styles, redraw, orig)

    # 备份未翻译框像素，防邻框擦除误伤
    kept_rois: list[tuple[tuple[int, int, int, int], np.ndarray]] = []
    for i, b in enumerate(boxes):
        if redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        kept_rois.append(((x1, y1, x2, y2), orig[y1:y2, x1:x2].copy()))

    # 两趟擦除：纯色只填文字带；非纯色局部取色；贯穿线图元先备份后回贴
    # PLAN-027g：擦除仍限原 OCR 框（保括号线/C10）；加厚文字带与 mask；
    # 带外回贴避开文字 mask（贯穿线强制回贴）；擦后再扫残留。
    img_h, img_w = img_cv.shape[:2]
    inpaint_mask = np.zeros(img_cv.shape[:2], np.uint8)
    fill_bands: list[tuple[int, int, int, int, int, int, np.ndarray | None] | None] = [
        None
    ] * len(boxes)
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        st = styles[i]
        roi = orig[y1:y2, x1:x2]
        tm_light = _text_mask_u8(roi, heavy=False)
        tm = _text_mask_u8(roi, heavy=True)
        guard = _line_guard_mask(roi, st["bg_bgr"], tm_light)
        guard_pix = None
        if guard.size and int(guard.max()) > 0:
            guard_pix = roi.copy()
        if st["solid"]:
            # 核心带（pad=2）整框填，加厚圈（pad=4）只擦文字 mask，避免涂掉括号线
            ty1, ty2 = _fill_band(roi, pad=2)
            by1, by2 = _fill_band(roi)
            fill_bands[i] = (x1, y1, x2, y2, by1, by2, tm.copy() if tm.size else None)
            fy1, fy2 = y1 + ty1, y1 + ty2
            cv2.rectangle(img_cv, (x1, fy1), (x2, fy2), st["bg_bgr"], -1)
            if tm.size and int(tm.max()) > 0:
                m = tm > 0
                if guard.size and int(guard.max()) > 0:
                    m = m & (guard == 0)
                # 加厚圈 + 带外残字：只按 mask 擦
                ring = np.ones(m.shape, bool)
                ring[ty1:ty2, :] = False
                img_cv[y1:y2, x1:x2][m & ring] = st["bg_bgr"]
        else:
            if tm.size:
                erase_tm = tm.copy()
                if guard.size and int(guard.max()) > 0:
                    erase_tm[guard > 0] = 0
                _erase_text_local(img_cv, x1, y1, x2, y2, erase_tm)
                inpaint_mask[y1:y2, x1:x2] = np.maximum(
                    inpaint_mask[y1:y2, x1:x2], erase_tm
                )
                fill_bands[i] = (x1, y1, x2, y2, 0, y2 - y1, tm.copy() if tm.size else None)
        if guard_pix is not None:
            g = guard > 0
            img_cv[y1:y2, x1:x2][g] = guard_pix[g]
    if int(inpaint_mask.max()) > 0:
        img_cv = cv2.inpaint(img_cv, inpaint_mask, 2, cv2.INPAINT_TELEA)
        for i, b in enumerate(boxes):
            if not redraw[i]:
                continue
            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            roi = orig[y1:y2, x1:x2]
            guard = _line_guard_mask(roi, styles[i]["bg_bgr"])
            if guard.size and int(guard.max()) > 0:
                g = guard > 0
                img_cv[y1:y2, x1:x2][g] = roi[g]

    # 文字带外整段回贴原图：挡住邻框填充/inpaint 越界抹掉的括号线、色带
    # PLAN-027g：回贴时排除文字 mask（但贯穿线强制回贴），禁止把残字贴回
    for i, fb in enumerate(fill_bands):
        if not fb:
            continue
        x1, y1, x2, y2, by1, by2, tm = fb
        avoid = None
        if tm is not None and tm.size and int(tm.max()) > 0:
            roi_o = orig[y1:y2, x1:x2]
            bg = tuple(int(c) for c in styles[i].get("bg_bgr", (255, 255, 255)))
            guard = _line_guard_mask(roi_o, bg, _text_mask_u8(roi_o, heavy=False))
            avoid = tm > 0
            if guard.size and int(guard.max()) > 0:
                avoid = avoid & (guard == 0)
        if by1 > 0:
            band = slice(y1, y1 + by1)
            if avoid is not None:
                m = ~avoid[:by1, :]
                img_cv[band, x1:x2][m] = orig[band, x1:x2][m]
            else:
                img_cv[band, x1:x2] = orig[band, x1:x2]
        if y1 + by2 < y2:
            band = slice(y1 + by2, y2)
            if avoid is not None:
                m = ~avoid[by2:, :]
                img_cv[band, x1:x2][m] = orig[band, x1:x2][m]
            else:
                img_cv[band, x1:x2] = orig[band, x1:x2]

    # PLAN-027g：擦除后二次扫描残留；仍检出则只擦文字像素（上限 1）
    leftover_cleared = _clear_ocr_leftovers(
        img_cv, boxes, styles, redraw, orig_texts=texts
    )
    if leftover_cleared:
        logger.info("cleared leftover OCR ink in %d boxes", leftover_cleared)
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        roi = orig[y1:y2, x1:x2]
        guard = _line_guard_mask(roi, styles[i]["bg_bgr"])
        if guard.size and int(guard.max()) > 0:
            img_cv[y1:y2, x1:x2][guard > 0] = roi[guard > 0]

    for (x1, y1, x2, y2), roi in kept_rois:
        img_cv[y1:y2, x1:x2] = roi

    erased_bgr = img_cv.copy()

    result = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(result)
    font_regular = _font()
    font_regular = font_regular if Path(font_regular).is_file() else None
    font_bold = _font_bold()
    if font_bold and not Path(font_bold).is_file():
        font_bold = None

    tier_meta = _assign_tier_sizes(
        boxes=boxes,
        texts=texts,
        finals=finals,
        redraw=redraw,
        styles=styles,
        avails=avails,
        orig=orig,
        font_regular=font_regular,
        font_bold=font_bold,
    )
    assigned = tier_meta["assigned"]
    tier_bold = tier_meta["tier_bold"]
    tiers = tier_meta["tiers"]

    drawn = 0
    min_contrast = 999.0
    sizes: list[int] = [0] * len(boxes)
    line_heights: list[int] = [0] * len(boxes)
    line_lists: list[list[str]] = [[] for _ in boxes]
    fonts: list = [None] * len(boxes)
    anchors: list[dict | None] = [None] * len(boxes)

    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        ax1, ay1, ax2, ay2 = avails[i]
        ox1, oy1, ox2, oy2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
        text = finals[i]
        st = styles[i]
        # 可用区只做换行宽度与溢出余量，排版基准改为原文墨迹
        box_w = max(8, ax2 - ax1)
        box_h = max(8, ay2 - ay1)
        geom = _ink_geometry(orig[oy1:oy2, ox1:ox2])
        # 主行：排除线状行后最宽的墨迹行，避开括号线/色带把整体 ink bbox 拉歪
        main = _main_row(geom.get("rows") or [])
        if main:
            ink_x1 = ox1 + int(main["x1"])
            ink_y1 = oy1 + int(main["y1"])
            ink_x2 = ox1 + int(main["x2"])
            ink_y2 = oy1 + int(main["y2"])
            ink_cx = ox1 + float(main["cx"])
            ink_cy = oy1 + (int(main["y1"]) + int(main["y2"])) / 2.0
        else:
            ink_x1 = ox1 + int(geom["ink_x1"])
            ink_y1 = oy1 + int(geom["ink_y1"])
            ink_x2 = ox1 + int(geom["ink_x2"])
            ink_y2 = oy1 + int(geom["ink_y2"])
            ink_cx = ox1 + float(geom["ink_cx"])
            ink_cy = oy1 + float(geom["ink_cy"])
        size = max(10, int(assigned[i]))
        use_bold = bool(styles[i].get("bold"))
        use_path = font_bold if use_bold and font_bold else font_regular
        if use_path:
            font = ImageFont.truetype(use_path, size)
        else:
            font = ImageFont.load_default()
        lh = _line_height(font, size)
        lines = _wrap_text(text, font, max(8, box_w))
        outlier_set = set(tier_meta.get("outliers") or [])
        if (i + 1) in outlier_set:
            while size > 10:
                total_h = lh * len(lines) + max(1, size // 8) * max(0, len(lines) - 1)
                max_tw = max((_text_size(font, ln)[0] for ln in lines), default=0)
                if max_tw <= box_w * 1.05 and total_h <= box_h:
                    break
                size -= 1
                if use_path:
                    font = ImageFont.truetype(use_path, size)
                lh = _line_height(font, size)
                lines = _wrap_text(text, font, max(8, box_w))
        # 非 outlier 不降字号，放不下由 C5 报告

        sizes[i] = size
        line_heights[i] = lh
        line_lists[i] = lines
        fonts[i] = font
        line_gap = max(1, size // 8)
        n_lines = max(1, len(lines))
        # 块墨迹高：行间距按 line box，末行只用墨迹高（避免 ascent/descent 空白偏移）
        last_ink_h = _text_size(font, lines[-1])[1] if lines else lh
        block_ink_h = (n_lines - 1) * (lh + line_gap) + max(1, last_ink_h)

        # 跨框左对齐组优先于逐框推断
        group_x = left_groups.get(i)
        align_mode = "left" if group_x is not None else st["align"]
        if group_x is not None:
            ink_x1 = int(round(group_x))

        # 竖向三段式：可证明不越界
        # - 实心彩色块：恒居中 ink_cy
        # - 其余且渲染块高 ≤ 原文墨迹高：居中（落在原 footprint 内）
        # - 其余且渲染块高 > 原文墨迹高：顶对齐向下生长
        orig_ink_h = max(1, ink_y2 - ink_y1)
        if st.get("solid_colored"):
            vertical_mode = "center"
            y0 = int(round(ink_cy - block_ink_h / 2.0))
        elif block_ink_h <= orig_ink_h:
            vertical_mode = "center"
            y0 = int(round(ink_cy - block_ink_h / 2.0))
        else:
            vertical_mode = "top"
            y0 = ink_y1

        # 先按锚点算各行理想坐标；x 一律表示墨迹左缘
        placements: list[tuple[int, int, str, int, int]] = []
        y_cursor = y0
        for ln in lines:
            bear_x, tw = _ink_x_metrics(font, ln)
            if align_mode == "left":
                x = ink_x1
            elif align_mode == "right":
                x = ink_x2 - tw
            else:
                x = int(round(ink_cx - tw / 2.0))
            placements.append((x, y_cursor, ln, tw, bear_x))
            y_cursor += lh + line_gap

        # 整块最小平移 clamp：
        # - 强锚（居中 / 实心彩色块 / 左对齐组成员 / 竖向居中）：仅钳图像边界
        # - 其余左/右对齐：clamp 进可用区，避免压邻框
        strict_anchor = (
            align_mode == "center"
            or st.get("solid_colored")
            or group_x is not None
            or vertical_mode == "center"
        )
        shift_x = 0
        shift_y = 0
        img_w = int(orig.shape[1])
        img_h = int(orig.shape[0])
        if placements:
            left = min(p[0] for p in placements)
            right = max(p[0] + p[3] for p in placements)
            top = placements[0][1]
            bottom = placements[0][1] + block_ink_h
            if strict_anchor:
                if left < 0:
                    shift_x = -left
                elif right > img_w:
                    shift_x = img_w - right
                if top < 0:
                    shift_y = -top
                elif bottom > img_h:
                    shift_y = img_h - bottom
            else:
                if left < ax1:
                    shift_x = ax1 - left
                elif right > ax2:
                    shift_x = ax2 - right
                if top < ay1:
                    shift_y = ay1 - top
                elif bottom > ay2:
                    shift_y = ay2 - bottom
                if top + shift_y < 0:
                    shift_y = -top
                elif bottom + shift_y > img_h:
                    shift_y = img_h - bottom
            if shift_x or shift_y:
                placements = [
                    (p[0] + shift_x, p[1] + shift_y, p[2], p[3], p[4])
                    for p in placements
                ]

        fill = _bgr_to_rgb(st["fg_bgr"])
        min_contrast = min(min_contrast, float(st["contrast"]))
        for x, y_ink, ln, tw, bear_x in placements:
            if tw > box_w * 1.15:
                logger.warning(
                    "text overflow box#%d w=%d need≈%d align=%s: %s",
                    i + 1,
                    box_w,
                    tw,
                    st["align"],
                    ln[:40],
                )
            # placements 里的 x/y 是墨迹左上角；扣掉左/上边距，否则「·」这类
            # 左边距大的字形会整体右移
            bear_y = font.getbbox(ln)[1] if hasattr(font, "getbbox") else 0
            d.text((x - bear_x, y_ink - bear_y), ln, fill=fill, font=font)
        draw_bbox = None
        if placements:
            draw_bbox = {
                "x1": min(p[0] for p in placements),
                "y1": placements[0][1],
                "x2": max(p[0] + p[3] for p in placements),
                "y2": placements[0][1] + block_ink_h,
            }
        anchors[i] = {
            "align": align_mode,
            "solid": bool(st.get("solid")),
            "solid_colored": bool(st.get("solid_colored")),
            "vertical_mode": vertical_mode,
            "left_group_x": (round(group_x, 1) if group_x is not None else None),
            "ink_src": {
                "x1": ink_x1,
                "y1": ink_y1,
                "x2": ink_x2,
                "y2": ink_y2,
                "cx": round(ink_cx, 1),
                "cy": round(ink_cy, 1),
            },
            "draw_bbox": draw_bbox,
            "shift": {"x": shift_x, "y": shift_y},
        }
        drawn += 1

    final_rgb = np.array(result)
    qc = _qc_report(
        out_path=out_path,
        boxes=boxes,
        texts=texts,
        trans=trans,
        redraw=redraw,
        drawn=drawn,
        styles=styles,
        avails=avails,
        sizes=sizes,
        line_heights=line_heights,
        line_lists=line_lists,
        fonts=fonts,
        erased_bgr=erased_bgr,
        final_rgb=final_rgb,
        tier_meta=tier_meta,
        orig_bgr=orig,
        anchors=anchors,
    )

    # PLAN-027a：译文墨迹区强制不透明，其余恢复原 Alpha
    draw_mask = None
    if alpha is not None:
        draw_mask = np.zeros(alpha.shape[:2], np.uint8)
        for anc in anchors:
            if not anc or not anc.get("draw_bbox"):
                continue
            bb = anc["draw_bbox"]
            x1 = max(0, int(bb["x1"]) - 1)
            y1 = max(0, int(bb["y1"]) - 1)
            x2 = min(draw_mask.shape[1], int(bb["x2"]) + 1)
            y2 = min(draw_mask.shape[0], int(bb["y2"]) + 1)
            if x2 > x1 and y2 > y1:
                draw_mask[y1:y2, x1:x2] = 255

    _save_with_alpha(result, out_path, alpha, draw_mask=draw_mask)
    kept = sum(1 for r in redraw if not r)
    solid_n = sum(1 for st in styles if st.get("solid"))
    logger.info(
        "translate_image: ocr=%d translated=%d drawn=%d kept_original=%d "
        "solid=%d/%d min_contrast=%.1f k=%.3f tiers=%d outliers=%s alpha=%s",
        len(boxes),
        sum(1 for i in range(len(boxes)) if trans.get(i + 1)),
        drawn,
        kept,
        solid_n,
        len(boxes),
        min_contrast if drawn else 0.0,
        float(tier_meta.get("k") or 0),
        len(tier_meta.get("orig_em") or {}),
        tier_meta.get("outliers") or [],
        alpha is not None,
    )
    return drawn, qc if isinstance(qc, dict) else {}


def translate_image_bytes(
    data: bytes, suffix: str = ".png", to_lang: str = "简体中文"
) -> tuple[bytes, int, dict]:
    """嵌字内存版，供 Word 内嵌图调用。返回 (bytes, blocks, qc)；失败则返回原字节、0、{}。"""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="img_ov_") as td:
        src = Path(td) / f"in{suffix}"
        dst = Path(td) / f"out{suffix}"
        src.write_bytes(data)
        try:
            n, qc = translate_image_with_qc(src, dst, to_lang=to_lang)
        except Exception as exc:
            logger.warning("image overlay failed, keep original: %s", exc)
            return data, 0, {}
        if n <= 0 or not dst.is_file():
            return data, 0, qc if isinstance(qc, dict) else {}
        return dst.read_bytes(), n, qc if isinstance(qc, dict) else {}


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dense_design.png"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/dense_design_zh.png"
    lang = sys.argv[3] if len(sys.argv) > 3 else "简体中文"
    t0 = time.time()
    n = translate_image(src, dst, to_lang=lang)
    print(f"翻译 {n} 个文字块 → {dst} ({time.time() - t0:.1f}s)")
