# SPDX-License-Identifier: MPL-2.0
"""图片嵌字：HPD 检测 → qwen3.6:35b-a3b 翻译 → opencv 擦除 → PIL 嵌字（PLAN-005c）。"""
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
    """HPD 检测+识别 → [(x1,y1,x2,y2,text,score), ...]"""
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
    # longest keys first
    for src in sorted(glossary.keys(), key=len, reverse=True):
        if src in text:
            text = text.replace(src, glossary[src])
    return text


def translate_texts(texts: list[str], model: str = MODEL, num_ctx: int = 8192) -> dict[int, str]:
    glossary = _load_glossary()
    prepared = [_apply_glossary(t, glossary) for t in texts]
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(prepared))
    prompt = (
        "/no_think Translate each numbered line to Simplified Chinese. "
        "Output ONLY the translation, keep the same numbering, no explanations:\n"
        f"{numbered}"
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": 2000},
        }
    ).encode()
    req = urllib.request.Request(
        f"{_ollama()}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        content = json.loads(r.read().decode())["message"]["content"]
    # strip think tags if any
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I).strip()
    trans: dict[int, str] = {}
    for line in content.split("\n"):
        m = re.match(r"(\d+)[.、)\s]+(.+)", line.strip())
        if m:
            trans[int(m.group(1))] = m.group(2).strip()
    return trans


def translate_image(img_path: str | Path, out_path: str | Path, to_lang: str = "中文") -> int:
    """完整图片嵌字翻译。失败返回 0（调用方应保留原图）。"""
    del to_lang  # reserved
    img_path = Path(img_path)
    out_path = Path(out_path)
    if os.environ.get("QYUNSLATION_IMAGE_OVERLAY", "1").lower() in ("0", "false", "off"):
        logger.info("image overlay disabled")
        return 0

    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        raise RuntimeError(f"cannot read image: {img_path}")
    orig = img_cv.copy()
    boxes = ocr_image_hpd(img_path)
    if not boxes:
        return 0

    texts = [b[4] for b in boxes]
    trans = translate_texts(texts)

    colors = []
    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        roi = orig[max(0, y1) : y2, max(0, x1) : x2]
        if roi.size == 0:
            colors.append((17, 17, 17))
            continue
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        vals = gray.flatten()
        vals = vals[vals < 120]
        color_val = int(vals.mean()) if len(vals) > 0 else 17
        colors.append((color_val, color_val, color_val))

    for b in boxes:
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        mask = np.zeros(img_cv.shape[:2], np.uint8)
        cv2.rectangle(mask, (x1 + 1, y1 + 1), (max(x1 + 2, x2 - 1), max(y1 + 2, y2 - 1)), 255, -1)
        img_cv = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)

    result = Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(result)
    font_path = _font()
    font_path = font_path if Path(font_path).is_file() else None
    for i, b in enumerate(boxes):
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        zh = trans.get(i + 1, "")
        if not zh:
            continue
        size = max(12, min(int((y2 - y1) * 0.9), 40))
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        d.text((x1, y1 - int(size * 0.1)), zh, fill=colors[i], font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(out_path)
    return len(boxes)


def translate_image_bytes(data: bytes, suffix: str = ".png") -> tuple[bytes, int]:
    """嵌字内存版，供 Word 内嵌图调用。失败则返回原字节、0。"""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="img_ov_") as td:
        src = Path(td) / f"in{suffix}"
        dst = Path(td) / f"out{suffix}"
        src.write_bytes(data)
        try:
            n = translate_image(src, dst)
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
    t0 = time.time()
    n = translate_image(src, dst)
    print(f"翻译 {n} 个文字块 → {dst} ({time.time() - t0:.1f}s)")
