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
TIER_BG_STEP = int(os.environ.get("QYUNSLATION_TIER_BG_STEP", "24"))
TIER_OUTLIER_RATIO = float(os.environ.get("QYUNSLATION_TIER_OUTLIER_RATIO", "0.6"))
TIER_RATIO_TOL = float(os.environ.get("QYUNSLATION_TIER_RATIO_TOL", "0.02"))
ALIGN_TOL_PX = float(os.environ.get("QYUNSLATION_ALIGN_TOL_PX", "12"))

_RAPID_ENGINE = None


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


def ocr_image(img_path: str | Path) -> list[tuple[int, int, int, int, str, float]]:
    """主 OCR：RapidOCR；零框时回退 HPD。"""
    try:
        boxes = ocr_image_rapid(img_path)
    except Exception as exc:
        logger.warning("RapidOCR failed, fallback HPD: %s", exc)
        boxes = []
    if boxes:
        logger.info("OCR RapidOCR: %d boxes", len(boxes))
        return boxes
    try:
        boxes = ocr_image_hpd(img_path)
        logger.info("OCR HPD fallback: %d boxes", len(boxes))
        return boxes
    except Exception as exc:
        logger.warning("HPD OCR also failed: %s", exc)
        return []


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
    align = _infer_align(geom.get("rows") or [], solid=solid)

    return {
        "bg_bgr": bg_bgr,
        "fg_bgr": fg_bgr,
        "border_bgr": border_bgr,
        "solid": solid,
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


def _infer_align(rows: list[dict], *, solid: bool = False) -> str:
    """多行比各行 x1/cx/x2 标准差，最小者即原文对齐；单行/实心色块取 center。"""
    # 实心色块上的标签在设计上几乎总是居中（流程图蓝框等）
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


def _text_mask_u8(roi: np.ndarray) -> np.ndarray:
    """Otsu 少数类作文字 mask（uint8 0/255），轻膨胀覆盖抗锯齿。"""
    if roi.size == 0:
        return np.zeros((0, 0), np.uint8)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask_hi = th > 0
    n_hi, n_lo = int(mask_hi.sum()), int((~mask_hi).sum())
    text = mask_hi if n_hi <= n_lo else ~mask_hi
    u8 = (text.astype(np.uint8) * 255)
    if u8.size:
        u8 = cv2.dilate(u8, np.ones((2, 2), np.uint8), iterations=1)
    return u8


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
        max_lines = max(1, box_h // max(1, lh))
        if len(lines) > max_lines:
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
        max_lines = max(1, box_h // max(1, best_lh))
        best_lines = best_lines[:max_lines]
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
        votes = sum(1 for i in idxs if bold_flags[i])
        tier_bold[t] = votes * 2 >= len(idxs)

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

    # C3 墨迹实测：最终相对只擦未写的变化像素（按可用区，因排版可能外扩）
    final_bgr = cv2.cvtColor(final_rgb, cv2.COLOR_RGB2BGR)
    blanks: list[int] = []
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = avails[i]
        ox1, oy1, ox2, oy2 = b[0], b[1], b[2], b[3]
        x1, y1 = min(x1, ox1), min(y1, oy1)
        x2, y2 = max(x2, ox2), max(y2, oy2)
        a = erased_bgr[y1:y2, x1:x2]
        c = final_bgr[y1:y2, x1:x2]
        if a.size == 0 or c.size == 0:
            blanks.append(i + 1)
            continue
        diff = np.abs(a.astype(np.int16) - c.astype(np.int16)).max(axis=2) > 8
        ratio = float(diff.mean()) if diff.size else 0.0
        if ratio < QC_INK_MIN:
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
            if not isinstance(db, dict):
                continue
            pad = 4
            mx1 = max(0, int(db["x1"]) - pad)
            my1 = max(0, int(db["y1"]) - pad)
            mx2 = min(iw, int(db["x2"]) + pad)
            my2 = min(ih, int(db["y2"]) + pad)
            dst_roi = final_bgr[my1:my2, mx1:mx2]
            dst_g = _ink_geometry(dst_roi)
            st = styles[i]
            align = st.get("align") or "center"
            # 计划锚点
            if st.get("solid"):
                sx = (int(db["x1"]) + int(db["x2"])) / 2.0
                sy = (int(db["y1"]) + int(db["y2"])) / 2.0
                dx_abs = mx1 + float(dst_g["ink_cx"])
                dy_abs = my1 + float(dst_g["ink_cy"])
            else:
                sy = float(db["y1"])
                dy_abs = my1 + float(dst_g["ink_y1"])
                if align == "left":
                    sx = float(db["x1"])
                    dx_abs = mx1 + float(dst_g["ink_x1"])
                elif align == "right":
                    sx = float(db["x2"])
                    dx_abs = mx1 + float(dst_g["ink_x2"])
                else:
                    sx = (int(db["x1"]) + int(db["x2"])) / 2.0
                    dx_abs = mx1 + float(dst_g["ink_cx"])
            ddx = dx_abs - sx
            ddy = dy_abs - sy
            ink_src = planned.get("ink_src") or {}
            # 相对原文锚点的位移（审计用）
            if st.get("solid"):
                src_ax = float(ink_src.get("cx") or ((ox1 + ox2) / 2.0))
                src_ay = float(ink_src.get("cy") or ((oy1 + oy2) / 2.0))
                plan_dx = sx - src_ax
                plan_dy = sy - src_ay
            else:
                src_ay = float(ink_src.get("y1") or oy1)
                plan_dy = sy - src_ay
                if align == "left":
                    src_ax = float(ink_src.get("x1") or ox1)
                elif align == "right":
                    src_ax = float(ink_src.get("x2") or ox2)
                else:
                    src_ax = float(ink_src.get("cx") or ((ox1 + ox2) / 2.0))
                plan_dx = sx - src_ax
            entry = {
                "box": i + 1,
                "align": align,
                "solid": bool(st.get("solid")),
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

    report = {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "drawn": drawn,
        "boxes": len(boxes),
        "solid_count": sum(1 for st in styles if st.get("solid")),
        "tiers": tiers_info,
        "k": (tier_meta or {}).get("k"),
        "outliers": (tier_meta or {}).get("outliers") or [],
        "align": align_details,
        "align_tol_px": ALIGN_TOL_PX,
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
        hard = [x for x in issues if x.get("code") in ("C1", "C2", "C3", "C4", "C8")]
        if hard:
            raise RuntimeError(f"image QC strict fail: {hard}")
    return report


def translate_image(
    img_path: str | Path, out_path: str | Path, to_lang: str = "简体中文"
) -> int:
    """完整图片嵌字翻译。返回实际绘制块数；失败返回 0（调用方应保留原图）。"""
    img_path = Path(img_path)
    out_path = Path(out_path)
    if os.environ.get("QYUNSLATION_IMAGE_OVERLAY", "1").lower() in ("0", "false", "off"):
        logger.info("image overlay disabled")
        return 0

    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        raise RuntimeError(f"cannot read image: {img_path}")
    orig = img_cv.copy()
    boxes = ocr_image(img_path)
    if not boxes:
        return 0

    texts = [b[4] for b in boxes]
    trans = translate_texts(texts, to_lang=to_lang)

    finals: list[str] = []
    redraw: list[bool] = []
    for i, src in enumerate(texts):
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

    # 备份未翻译框像素，防邻框擦除误伤
    kept_rois: list[tuple[tuple[int, int, int, int], np.ndarray]] = []
    for i, b in enumerate(boxes):
        if redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        kept_rois.append(((x1, y1, x2, y2), orig[y1:y2, x1:x2].copy()))

    # 两趟擦除：纯色填充；非纯色局部邻域取色（保留色带），必要时一次 inpaint 收尾
    inpaint_mask = np.zeros(img_cv.shape[:2], np.uint8)
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        st = styles[i]
        if st["solid"]:
            cv2.rectangle(img_cv, (x1, y1), (x2, y2), st["bg_bgr"], -1)
        else:
            roi = orig[y1:y2, x1:x2]
            tm = _text_mask_u8(roi)
            if tm.size:
                _erase_text_local(img_cv, x1, y1, x2, y2, tm)
                inpaint_mask[y1:y2, x1:x2] = np.maximum(
                    inpaint_mask[y1:y2, x1:x2], tm
                )
    if int(inpaint_mask.max()) > 0:
        img_cv = cv2.inpaint(img_cv, inpaint_mask, 2, cv2.INPAINT_TELEA)

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
        # 主行：最宽墨迹行，避开括号线/色带把整体 ink bbox 拉歪
        rows = geom.get("rows") or []
        if rows:
            main = max(rows, key=lambda r: int(r["x2"]) - int(r["x1"]))
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
        use_bold = bool(tier_bold.get(tiers[i]))
        use_path = font_bold if use_bold and font_bold else font_regular
        if use_path:
            font = ImageFont.truetype(use_path, size)
        else:
            font = ImageFont.load_default()
        lh = _line_height(font, size)
        lines = _wrap_text(text, font, max(8, box_w))
        max_lines = max(1, box_h // max(1, lh))
        lines = lines[:max_lines]
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
                max_lines = max(1, box_h // max(1, lh))
                lines = lines[:max_lines]
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

        if st.get("solid"):
            # 实心块：整块墨迹垂直中心对齐原文 ink_cy，上下对称生长
            y0 = int(round(ink_cy - block_ink_h / 2.0))
        else:
            # 自由文字：首行墨迹顶对齐原文 ink_y1，向下生长
            y0 = ink_y1

        # 先按锚点算各行理想坐标
        placements: list[tuple[int, int, str, int]] = []  # x, y_ink_top, ln, tw
        y_cursor = y0
        for ln in lines:
            tw, _ = _text_size(font, ln)
            if st["align"] == "left":
                x = ink_x1
            elif st["align"] == "right":
                x = ink_x2 - tw
            else:
                x = int(round(ink_cx - tw / 2.0))
            placements.append((x, y_cursor, ln, tw))
            y_cursor += lh + line_gap

        # 整块最小平移 clamp：
        # - 居中（含实心色块）：禁止被不对称可用区推偏，仅钳到图像边界
        # - 左/右对齐：clamp 进可用区，避免压邻框
        # - 非居中纵向：clamp 进可用区
        shift_x = 0
        shift_y = 0
        img_w = int(orig.shape[1])
        img_h = int(orig.shape[0])
        if placements:
            left = min(p[0] for p in placements)
            right = max(p[0] + p[3] for p in placements)
            top = placements[0][1]
            bottom = placements[0][1] + block_ink_h
            if st["align"] == "center" or st.get("solid"):
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
                    (p[0] + shift_x, p[1] + shift_y, p[2], p[3]) for p in placements
                ]

        fill = _bgr_to_rgb(st["fg_bgr"])
        min_contrast = min(min_contrast, float(st["contrast"]))
        for x, y_ink, ln, tw in placements:
            if tw > box_w * 1.15:
                logger.warning(
                    "text overflow box#%d w=%d need≈%d align=%s: %s",
                    i + 1,
                    box_w,
                    tw,
                    st["align"],
                    ln[:40],
                )
            top = 0
            if hasattr(font, "getbbox"):
                bb = font.getbbox(ln)
                top = bb[1]
            d.text((x, y_ink - top), ln, fill=fill, font=font)
        draw_bbox = None
        if placements:
            draw_bbox = {
                "x1": min(p[0] for p in placements),
                "y1": placements[0][1],
                "x2": max(p[0] + p[3] for p in placements),
                "y2": placements[0][1] + block_ink_h,
            }
        anchors[i] = {
            "align": st["align"],
            "solid": bool(st.get("solid")),
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
    _qc_report(
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    kept = sum(1 for r in redraw if not r)
    solid_n = sum(1 for st in styles if st.get("solid"))
    logger.info(
        "translate_image: ocr=%d translated=%d drawn=%d kept_original=%d "
        "solid=%d/%d min_contrast=%.1f k=%.3f tiers=%d outliers=%s",
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
    )
    return drawn


def translate_image_bytes(
    data: bytes, suffix: str = ".png", to_lang: str = "简体中文"
) -> tuple[bytes, int]:
    """嵌字内存版，供 Word 内嵌图调用。失败则返回原字节、0。"""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="img_ov_") as td:
        src = Path(td) / f"in{suffix}"
        dst = Path(td) / f"out{suffix}"
        src.write_bytes(data)
        try:
            n = translate_image(src, dst, to_lang=to_lang)
        except Exception as exc:
            logger.warning("image overlay failed, keep original: %s", exc)
            return data, 0
        if n <= 0 or not dst.is_file():
            return data, 0
        return dst.read_bytes(), n


if __name__ == "__main__":
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dense_design.png"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/dense_design_zh.png"
    lang = sys.argv[3] if len(sys.argv) > 3 else "简体中文"
    t0 = time.time()
    n = translate_image(src, dst, to_lang=lang)
    print(f"翻译 {n} 个文字块 → {dst} ({time.time() - t0:.1f}s)")
