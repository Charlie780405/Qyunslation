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
MODEL = (
    os.environ.get("QYUNSLATION_MODEL_ID")
    or os.environ.get("DOCUTRANSLATE_MODEL_ID")
    or "qwen3.6:35b-a3b"
)
GLOSSARY_CSV = os.environ.get("QYUNSLATION_GLOSSARY_CSV") or ""

OCR_MIN_SCORE = float(os.environ.get("QYUNSLATION_OCR_MIN_SCORE", "0.5"))
TRANSLATE_BATCH = int(os.environ.get("QYUNSLATION_TRANSLATE_BATCH", "25"))
NUM_PREDICT = int(os.environ.get("QYUNSLATION_NUM_PREDICT", "4096"))

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


def _text_size(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return font.getsize(text)  # type: ignore[attr-defined]


def _wrap_text(text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    """按词/字换行，使每行宽度不超过 max_w。"""
    if max_w <= 0:
        return [text]
    # 英文按空格，中文按字
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
) -> tuple[ImageFont.ImageFont, list[str], int]:
    """二分字号：优先单行，放不下则换行；返回 (font, lines, size)。"""
    lo, hi = min_size, max(min_size, max_size)
    best_font = ImageFont.load_default()
    best_lines = [text]
    best_size = min_size

    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid) if font_path else ImageFont.load_default()
        tw, th = _text_size(font, text)
        if tw <= box_w and th <= box_h:
            best_font, best_lines, best_size = font, [text], mid
            lo = mid + 1
            continue
        # 尝试换行
        lines = _wrap_text(text, font, max(8, box_w))
        line_h = max((_text_size(font, ln)[1] for ln in lines), default=th)
        total_h = line_h * len(lines) + max(0, len(lines) - 1) * max(1, mid // 8)
        max_line_w = max((_text_size(font, ln)[0] for ln in lines), default=tw)
        if max_line_w <= box_w * 1.05 and total_h <= box_h:
            best_font, best_lines, best_size = font, lines, mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best_size == min_size and font_path:
        best_font = ImageFont.truetype(font_path, min_size)
        best_lines = _wrap_text(text, best_font, max(8, box_w))
    return best_font, best_lines, best_size


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

    # 最终要写的文字：有译文用译文，无译文回退原文（绝不净擦除）
    finals: list[str] = []
    redraw: list[bool] = []
    for i, src in enumerate(texts):
        zh = (trans.get(i + 1) or "").strip()
        if zh and zh != src:
            finals.append(zh)
            redraw.append(True)
        elif zh:
            # 译文与原文相同（专名/缩写）：仍重绘以统一字体，但不算丢字
            finals.append(zh)
            redraw.append(True)
        else:
            finals.append(src)
            redraw.append(False)  # 缺译：保留原像素，不擦不画

    colors = []
    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        roi = orig[max(0, y1):y2, max(0, x1):x2]
        if roi.size == 0:
            colors.append((17, 17, 17))
            continue
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        vals = gray.flatten()
        vals = vals[vals < 120]
        color_val = int(vals.mean()) if len(vals) > 0 else 17
        colors.append((color_val, color_val, color_val))

    # 只擦将要重绘的框
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        mask = np.zeros(img_cv.shape[:2], np.uint8)
        cv2.rectangle(
            mask,
            (x1 + 1, y1 + 1),
            (max(x1 + 2, x2 - 1), max(y1 + 2, y2 - 1)),
            255,
            -1,
        )
        img_cv = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)

    result = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(result)
    font_path = _font()
    font_path = font_path if Path(font_path).is_file() else None
    drawn = 0
    for i, b in enumerate(boxes):
        if not redraw[i]:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        text = finals[i]
        box_w = max(8, x2 - x1)
        box_h = max(8, y2 - y1)
        max_size = max(12, min(int(box_h * 0.9), 40))
        font, lines, size = _fit_font_and_lines(text, box_w, box_h, font_path, max_size)
        line_gap = max(1, size // 8)
        line_h = max((_text_size(font, ln)[1] for ln in lines), default=size)
        total_h = line_h * len(lines) + line_gap * max(0, len(lines) - 1)
        y = y1 + max(0, (box_h - total_h) // 2) - int(size * 0.05)
        for ln in lines:
            tw, _ = _text_size(font, ln)
            if tw > box_w * 1.15:
                logger.warning(
                    "text overflow box#%d w=%d need≈%d: %s",
                    i + 1,
                    box_w,
                    tw,
                    ln[:40],
                )
            d.text((x1, y), ln, fill=colors[i], font=font)
            y += line_h + line_gap
        drawn += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    kept = sum(1 for r in redraw if not r)
    logger.info(
        "translate_image: ocr=%d translated=%d drawn=%d kept_original=%d",
        len(boxes),
        sum(1 for i in range(len(boxes)) if trans.get(i + 1)),
        drawn,
        kept,
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
