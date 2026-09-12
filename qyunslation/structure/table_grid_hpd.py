# SPDX-License-Identifier: MPL-2.0
"""PLAN-048a：HPD 视觉解析拿表格逻辑网格（只取结构，不取文本入译文）。

HPD 出行列/合并格；PDF 文字层出精确字形与墨迹框。HPD OCR 错字实证
（neutralizing studies / O2W / ECZTRA）→ 文本一律取文字层。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

HPD_URL_DEFAULT = "http://100.67.66.123:8120"
HPD_TIMEOUT = 180
HPD_HEALTH_TIMEOUT = 5
CLIP_PAD_TOP = 24.0
CLIP_PAD_BOTTOM = 28.0
CLIP_PAD_X = 6.0
CLIP_DPI = 200

_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.I | re.S)
_TD_RE = re.compile(r"<t[dh]([^>]*)>(.*?)</t[dh]>", re.I | re.S)
_COLSPAN_RE = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_LATEX_CMD_RE = re.compile(r"\\(?:mathrm|mathbf|mathit|textrm|textit|textbf|text)\s*\{([^{}]*)\}")
_LATEX_SUPER_RE = re.compile(r"\^\{([^{}]*)\}|\^([A-Za-z0-9])")
_LATEX_WRAP_RE = re.compile(r"\\\(|\\\)|\\\[|\\\]")
_LATEX_BRACE_RE = re.compile(r"[{}]")
_COORD_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)+\s*\]")
_N_EQ_RE = re.compile(r"^N\s*=\s*\d+", re.I)
_CHILD_RE = re.compile(r"<CHILD>(.*)$")
_BLOCK_LINE_RE = re.compile(r"^<BLOCK>(\w+)\s*\[[^\]]*\]\s*(.*)$")


@dataclass
class HpdGrid:
    """HPD 逻辑网格。rows[i][j] 是 HPD OCR 文本，仅供对齐，禁止写入译文。"""

    rows: list[list[str]] = field(default_factory=list)
    colspans: list[list[int]] = field(default_factory=list)
    n_cols: int = 0
    source_md: str = ""
    not_a_table: bool = False
    error: str | None = None
    cached: bool = False

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def hpd_mode() -> str:
    """QYUNSLATION_HPD_GRID=hpd|gutter|off。默认 hpd。"""
    raw = (os.environ.get("QYUNSLATION_HPD_GRID") or "hpd").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return "off"
    if raw in {"gutter", "gap", "whitespace"}:
        return "gutter"
    return "hpd"


def hpd_base_url() -> str:
    return (
        os.environ.get("QYUNSLATION_HPD_BASE_URL")
        or os.environ.get("QYUNSLATION_HPD_URL")
        or HPD_URL_DEFAULT
    ).rstrip("/")


def cache_dir() -> Path:
    override = os.environ.get("QYUNSLATION_HPD_GRID_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "qyunslation" / "hpd-grid"


def hpd_health(*, timeout: int = HPD_HEALTH_TIMEOUT) -> bool:
    """5s 探测；不可达一律 False，绝不抛。"""
    try:
        with urllib.request.urlopen(f"{hpd_base_url()}/health", timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "ok"
    except Exception:
        return False


def _delatex(text: str) -> str:
    """PLAN-048a：剥离 HPD LaTeX 上下标，保留可读字母。

    例：``\\( {\\mathrm{{ADA}}}^{\\mathrm{a}} \\)`` → ``ADAa``
    """
    raw = text or ""
    raw = raw.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    prev = None
    while prev != raw:
        prev = raw
        raw = re.sub(r"\{\{([^{}]*)\}\}", r"{\1}", raw)
        raw = _LATEX_CMD_RE.sub(r"\1", raw)
    raw = _LATEX_SUPER_RE.sub(r"\1\2", raw)
    raw = _LATEX_WRAP_RE.sub("", raw)
    raw = _LATEX_BRACE_RE.sub("", raw)
    raw = raw.replace("\\", "")
    raw = _TAG_RE.sub(" ", raw)
    raw = raw.replace("\u00a0", " ").replace("\u2011", "-").replace("\u2013", "-")
    raw = re.sub(
        r"\b(?:mathrm|mathbf|mathit|textrm|textit|textbf|text)\b",
        "",
        raw,
    )
    return " ".join(raw.split()).strip()


def _clean_cell(text: str) -> str:
    return _delatex(text)


def _hpd_to_markdown(raw: str) -> str:
    """HPD <BLOCK>/<CHILD> 流 → markdown（去坐标）。"""
    if not raw:
        return ""
    out: list[str] = []
    for line in raw.split("\n"):
        line = line.rstrip()
        m = _CHILD_RE.search(line)
        if m:
            content = m.group(1)
        else:
            m2 = _BLOCK_LINE_RE.match(line)
            content = m2.group(2) if m2 else line
        content = _COORD_RE.sub("", content).strip()
        if content:
            out.append(content)
    return "\n".join(out)


def _parse_html_table(html: str) -> tuple[list[list[str]], list[list[int]]]:
    """解析 <table> → (rows, colspans)。跨列按 colspan 展开占位。"""
    rows: list[list[str]] = []
    spans: list[list[int]] = []
    for tr in _TR_RE.findall(html):
        cells: list[str] = []
        cell_spans: list[int] = []
        for attrs, body in _TD_RE.findall(tr):
            text = _clean_cell(body)
            m = _COLSPAN_RE.search(attrs or "")
            span = max(1, int(m.group(1))) if m else 1
            cells.append(text)
            cell_spans.append(span)
            for _ in range(span - 1):
                cells.append("")
                cell_spans.append(0)
        if any(c.strip() for c in cells):
            rows.append(cells)
            spans.append(cell_spans)
    return rows, spans


def _markdown_pipe_rows(md: str) -> tuple[list[list[str]], list[list[int]]]:
    rows: list[list[str]] = []
    spans: list[list[int]] = []
    for line in md.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            continue
        parts = [p.strip() for p in s.strip("|").split("|")]
        cells = [_clean_cell(p) for p in parts]
        if any(cells):
            rows.append(cells)
            spans.append([1] * len(cells))
    return rows, spans


def parse_hpd_grid_markdown(md: str) -> HpdGrid:
    """从 HPD markdown/HTML 抽出网格。无 <table> 且管道表 <2 行 → not_a_table。"""
    clean = _hpd_to_markdown(md) if "<BLOCK>" in (md or "") else (md or "")
    rows: list[list[str]] = []
    spans: list[list[int]] = []
    if "<table" in clean.lower():
        # 可能多块；取最大表
        best: tuple[list[list[str]], list[list[int]]] = ([], [])
        for m in re.finditer(r"<table[\s\S]*?</table>", clean, re.I):
            r, s = _parse_html_table(m.group(0))
            if len(r) > len(best[0]):
                best = (r, s)
        rows, spans = best
    if len(rows) < 2:
        pipe_rows, pipe_spans = _markdown_pipe_rows(clean)
        if len(pipe_rows) > len(rows):
            rows, spans = pipe_rows, pipe_spans
    if len(rows) < 2:
        return HpdGrid(rows=[], colspans=[], n_cols=0, source_md=clean, not_a_table=True)
    rows, spans = _merge_wrapped_rows(rows, spans)
    width = max((len(r) for r in rows), default=0)
    norm_rows = [(r + [""] * width)[:width] for r in rows]
    norm_spans = [(s + [1] * width)[:width] for s in spans]
    return HpdGrid(
        rows=norm_rows,
        colspans=norm_spans,
        n_cols=width,
        source_md=clean,
        not_a_table=False,
    )


def _merge_wrapped_rows(
    rows: list[list[str]], spans: list[list[int]]
) -> tuple[list[list[str]], list[list[int]]]:
    """PLAN-048a：合并软折行（前行数据格以逗号收尾，或后行几乎全是 N=…）。"""
    if len(rows) < 2:
        return rows, spans
    out_rows: list[list[str]] = [list(rows[0])]
    out_spans: list[list[int]] = [list(spans[0]) if spans else [1] * len(rows[0])]
    for i in range(1, len(rows)):
        prev = out_rows[-1]
        cur = rows[i]
        cur_span = spans[i] if i < len(spans) else [1] * len(cur)
        if _should_merge_wrap(prev, cur):
            merged = list(prev)
            width = max(len(merged), len(cur))
            merged = (merged + [""] * width)[:width]
            cur_pad = (list(cur) + [""] * width)[:width]
            for j in range(width):
                a, b = merged[j].strip(), cur_pad[j].strip()
                if not b:
                    continue
                if not a:
                    merged[j] = b
                elif a.endswith(",") or a.endswith("，"):
                    merged[j] = f"{a} {b}".strip()
                else:
                    merged[j] = f"{a} {b}".strip()
            out_rows[-1] = merged
            # 保留前一行 colspan
            continue
        out_rows.append(list(cur))
        out_spans.append(list(cur_span))
    return out_rows, out_spans


def _should_merge_wrap(prev: list[str], cur: list[str]) -> bool:
    prev_data = [c.strip() for c in prev[1:] if c and c.strip()]
    cur_data = [c.strip() for c in cur if c and c.strip()]
    if not cur_data:
        return False
    # 后行几乎全是 N=…
    n_eq = sum(1 for c in cur_data if _N_EQ_RE.match(c))
    if n_eq >= max(1, len(cur_data) - 1) and n_eq >= 1:
        return True
    # 前行数据格以逗号收尾
    if prev_data and sum(1 for c in prev_data if c.endswith(",") or c.endswith("，")) >= max(
        1, len(prev_data) // 2
    ):
        return True
    return False


def _clip_png(page, region, *, dpi: int = CLIP_DPI) -> tuple[bytes, str]:
    """裁区域 PNG；返回 (png_bytes, sha256_hex)。"""
    import pymupdf

    page_w = float(page.rect.width)
    page_h = float(page.rect.height)
    x0 = max(0.0, float(region.x0) - CLIP_PAD_X)
    y0 = max(0.0, float(region.y0) - CLIP_PAD_TOP)
    x1 = min(page_w, float(region.x1) + CLIP_PAD_X)
    y1 = min(page_h, float(region.y1) + CLIP_PAD_BOTTOM)
    clip = pymupdf.Rect(x0, y0, x1, y1)
    png = page.get_pixmap(dpi=dpi, clip=clip, alpha=False).tobytes("png")
    digest = hashlib.sha256(png).hexdigest()
    return png, digest


def _cache_path(digest: str) -> Path:
    return cache_dir() / f"{digest}.json"


def _load_cache(digest: str) -> HpdGrid | None:
    path = _cache_path(digest)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    grid = HpdGrid(
        rows=data.get("rows") or [],
        colspans=data.get("colspans") or [],
        n_cols=int(data.get("n_cols") or 0),
        source_md=str(data.get("source_md") or ""),
        not_a_table=bool(data.get("not_a_table")),
        error=data.get("error"),
        cached=True,
    )
    return grid


def _save_cache(digest: str, grid: HpdGrid) -> None:
    try:
        path = _cache_path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rows": grid.rows,
            "colspans": grid.colspans,
            "n_cols": grid.n_cols,
            "source_md": grid.source_md,
            "not_a_table": grid.not_a_table,
            "error": grid.error,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("hpd grid cache write failed: %s", exc)


def _call_hpd(png: bytes, *, timeout: int = HPD_TIMEOUT) -> tuple[str, str | None]:
    """POST /parse；返回 (markdown, error)。失败不抛。"""
    import base64

    url = f"{hpd_base_url()}/parse"
    payload = json.dumps({"image_b64": base64.b64encode(png).decode()}).encode()
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        if data.get("error"):
            return "", str(data["error"])
        return data.get("markdown") or "", None
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def hpd_grid(page, region, *, dpi: int = CLIP_DPI, force: bool = False) -> HpdGrid:
    """对表格区域跑 HPD，返回逻辑网格。

    - mode=off → 空网格 + error=off
    - 不可达 / 解析失败 → error 非空，调用方降级
    - 无 <table> → not_a_table=True
    """
    mode = hpd_mode()
    if mode == "off":
        return HpdGrid(error="off")
    if mode == "gutter":
        return HpdGrid(error="gutter_mode")

    try:
        png, digest = _clip_png(page, region, dpi=dpi)
    except Exception as exc:
        return HpdGrid(error=f"clip:{type(exc).__name__}: {exc}")

    if not force:
        cached = _load_cache(digest)
        if cached is not None:
            return cached

    if not hpd_health():
        grid = HpdGrid(error="unreachable")
        return grid

    raw, err = _call_hpd(png)
    if err or not raw:
        return HpdGrid(error=err or "empty")
    grid = parse_hpd_grid_markdown(raw)
    _save_cache(digest, grid)
    return grid


def normalize_for_align(text: str) -> str:
    """对齐用归一化：去空格/大小写/LaTeX/全半角差异。"""
    t = _delatex(text or "")
    # 全角 → 半角数字字母常见符
    out = []
    for ch in t:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch in {"\u3000", "\xa0"}:
            out.append(" ")
        else:
            out.append(ch)
    t = "".join(out)
    t = t.replace("µ", "u").replace("μ", "u").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", "", t)
    return t.lower()
