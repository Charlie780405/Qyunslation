# SPDX-License-Identifier: MPL-2.0
"""拍照/扫描 PDF → 泰州 HPD 铺不可见文字层。供 pdf2zh 进程直接 import。"""
from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

HPD_URL = "http://100.67.66.123:8120"
_BLOCK_RE = re.compile(
    r"<BLOCK>(?P<type>\w+)\s+\[(?P<x1>\d+),\s*(?P<y1>\d+),\s*(?P<x2>\d+),\s*(?P<y2>\d+)\]"
    r"<CHILD>(?P<text>.+)$"
)


def _parse(url: str, image_b64: str, timeout: int = 180) -> str:
    req = urllib.request.Request(
        f"{url.rstrip('/')}/parse",
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


def pdf_needs_hpd(src: Path, min_chars: int = 80) -> bool:
    import pymupdf

    doc = pymupdf.open(src)
    try:
        text = "".join((p.get_text() or "") for p in doc)
    finally:
        doc.close()
    return len(text.strip()) < min_chars


def ocr_pdf_with_hpd(
    src: Path,
    dest: Path | None = None,
    *,
    dpi: int = 150,
    progress_cb=None,
) -> Path:
    import pymupdf

    src = Path(src)
    dest = dest or src.with_name(f"{src.stem}.hpd-ocr.pdf")
    dest = Path(dest)
    doc = pymupdf.open(src)
    written = 0
    total = len(doc)
    for i, page in enumerate(doc):
        if progress_cb:
            progress_cb(i + 1, total)
        pix = page.get_pixmap(dpi=dpi)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
        try:
            raw = _parse(HPD_URL, b64)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            logger.warning("HPD 第 %s 页失败: %s", i + 1, exc)
            continue
        blocks = _blocks(raw)
        pw, ph = page.rect.width, page.rect.height
        sx, sy = pw / max(pix.width, 1), ph / max(pix.height, 1)
        max_x = max((b[2] for b in blocks), default=0)
        max_y = max((b[3] for b in blocks), default=0)
        if max(max_x, max_y) <= 1000 and (pix.width > 1200 or pix.height > 1200):
            sx, sy = pw / 1000.0, ph / 1000.0
        for x1, y1, x2, y2, text in blocks:
            box = pymupdf.Rect(x1 * sx, y1 * sy, max(x2 * sx, x1 * sx + 8), max(y2 * sy, y1 * sy + 8))
            try:
                page.insert_textbox(
                    box,
                    text,
                    fontsize=max(6, min(18, (box.y1 - box.y0) * 0.85)),
                    render_mode=3,
                    overlay=True,
                )
                written += 1
            except Exception:
                continue
        logger.info("HPD 第 %s 页 %s 块", i + 1, len(blocks))
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    if written == 0:
        raise RuntimeError("HPD 未识别到文字")
    return dest
