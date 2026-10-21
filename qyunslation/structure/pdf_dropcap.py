# SPDX-License-Identifier: MPL-2.0
"""PLAN-084: 首字下沉（drop cap）——译前还原为行内字母，译后在中文里放大首字。

问题：期刊正文常以 28pt 大写字母开头（``A`` + ``topic dermatitis``）。BabelDOC 把大字与后面小字当作公式/上下标，
中文只译出「特…应性」，英文 ``topic`` 作为公式残片原样留在错位的位置，压在上方小标题（Introduction）上。

做法（失败一律保持原样，不阻断交付）：
1. ``normalize_dropcaps``：译前在送翻译的副本里把大字母擦掉，按正文字号写回「首词之前」，让整段是普通文本。
2. ``emphasize_zh_first_char``：译后找到该段中文首行，首字加粗并放大，其余字符按原位置等比收紧，右缘不变。
3. ``restore_dual_source_half``：双语 PDF 左半是送翻译的副本，用原件页覆盖回去，原文侧仍是真正的首字下沉。
"""
from __future__ import annotations

import hashlib
import os
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_FONT_DIR = Path(os.environ.get("QYUNSLATION_BABELDOC_FONT_DIR", str(Path.home() / ".cache" / "babeldoc" / "fonts")))
_SUBSET_DIR = Path(os.environ.get("QYUNSLATION_FONT_SUBSET_DIR", "/tmp/qyunslation-font-subsets"))
_BOLD_FONT = "SourceHanSerifCN-Bold"
_FALLBACK_LATIN = "NotoSerif-Regular"


def dropcap_enabled() -> bool:
    return (os.environ.get("QYUNSLATION_FIX_DROPCAP") or "1").strip().casefold() not in {"0", "false", "off", "no"}


def zh_scale() -> float:
    try:
        return max(1.0, min(2.0, float(os.environ.get("QYUNSLATION_DROPCAP_ZH_SCALE") or "1.4")))
    except ValueError:
        return 1.4


@dataclass
class DropCap:
    page: int  # 0-based
    char: str
    cap_size: float
    body_size: float
    col_x0: float  # 大字母左缘，即版心左缘
    line_y0: float  # 首个正文词所在行（原文）的上下缘
    line_y1: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _import_fitz():
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError:
        import fitz  # type: ignore[import-not-found,no-redef]
    return fitz


def _spans(page):
    for block in page.get_text("rawdict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            yield line, line.get("spans", [])


def _span_text(span) -> str:
    return "".join(ch["c"] for ch in span.get("chars", []))


def _find_on_page(page, pno: int):
    """yield (DropCap, cap_span, next_span)。大字母常自成一行，首词在另一行，所以按几何而不是按行配对。"""
    flat = [span for _line, spans in _spans(page) for span in spans if _span_text(span).strip()]
    sizes = [float(sp["size"]) for sp in flat for _ in _span_text(sp).strip()]
    if len(sizes) < 40:
        return
    body = statistics.median(sizes)
    for cap in flat:
        text = _span_text(cap).strip()
        size = float(cap["size"])
        if not (len(text) == 1 and text.isalpha() and text.isupper() and 1.8 * body <= size <= 8 * body):
            continue
        cx1, cy0 = float(cap["bbox"][2]), float(cap["bbox"][1])
        cands = [
            sp
            for sp in flat
            if sp is not cap
            and abs(float(sp["size"]) - body) <= 0.2 * body
            and -1.0 <= float(sp["bbox"][0]) - cx1 <= 6.0
            and cy0 - 2.0 <= float(sp["bbox"][1]) <= cy0 + 0.6 * size
        ]
        if not cands:
            continue
        nxt = min(cands, key=lambda sp: float(sp["bbox"][1]))
        rec = DropCap(
            page=pno,
            char=text,
            cap_size=size,
            body_size=body,
            col_x0=float(cap["bbox"][0]),
            line_y0=float(nxt["bbox"][1]),
            line_y1=float(nxt["bbox"][3]),
        )
        yield rec, cap, nxt


def detect_dropcaps(doc) -> list[DropCap]:
    return [rec for pno in range(len(doc)) for rec, _cap, _nxt in _find_on_page(doc[pno], pno)]


_TM_RE = re.compile(
    r"(?P<a>-?\d*\.?\d+)\s+0\s+0\s+(?P<d>-?\d*\.?\d+)\s+(?P<e>-?\d*\.?\d+)\s+(?P<f>-?\d*\.?\d+)\s+Tm"
)


def _num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _patch_stream(data: str, rec: DropCap, cap, nxt, page_height: float, advance: float) -> str | None:
    """把大字母的文本矩阵改成「正文字号、首词之前」，字符本身留在内容流原位，阅读顺序不变。"""
    cap_x = float(cap["chars"][0]["origin"][0])
    cap_y = page_height - float(cap["chars"][0]["origin"][1])
    for match in _TM_RE.finditer(data):
        a, d, e, f = (float(match.group(k)) for k in ("a", "d", "e", "f"))
        if abs(a - rec.cap_size) > 0.05 or abs(d - rec.cap_size) > 0.05 or abs(e - cap_x) > 0.1 or abs(f - cap_y) > 0.2:
            continue
        new_x = float(nxt["bbox"][0]) - advance - 0.1
        new_y = page_height - float(nxt["chars"][0]["origin"][1])
        replacement = f"{_num(rec.body_size)} 0 0 {_num(rec.body_size)} {_num(new_x)} {_num(new_y)} Tm"
        return data[: match.start()] + replacement + data[match.end() :]
    return None


def normalize_dropcaps(src: Path, dst: Path) -> list[DropCap]:
    """写出 ``dst``（仅在有改动时），返回处理过的首字下沉。"""
    if not dropcap_enabled() or not src.is_file():
        return []
    fitz = _import_fitz()
    doc = fitz.open(str(src))
    try:
        done: list[DropCap] = []
        for pno in range(len(doc)):
            page = doc[pno]
            found = list(_find_on_page(page, pno))
            if not found:
                continue
            try:
                page.clean_contents()
                xrefs = page.get_contents()
                if len(xrefs) != 1:
                    continue
                data = doc.xref_stream(xrefs[0]).decode("latin-1")
                height = float(page.rect.height)
                for rec, cap, nxt in found:
                    advance = (float(cap["bbox"][2]) - float(cap["bbox"][0])) * rec.body_size / rec.cap_size
                    patched = _patch_stream(data, rec, cap, nxt, height, advance)
                    if patched is None:
                        continue
                    data = patched
                    done.append(rec)
                if done and done[-1].page == pno:
                    doc.update_stream(xrefs[0], data.encode("latin-1"))
            except Exception:  # noqa: BLE001
                continue
        if done:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix(dst.suffix + ".dctmp")
            doc.save(str(tmp), garbage=0, deflate=True)
            tmp.replace(dst)
        return done
    finally:
        doc.close()


# ---- post-translation -------------------------------------------------------------------------------


def _font_file(name: str) -> Path | None:
    stem = re.sub(r"^[A-Z]{6}\+", "", name or "")
    path = _FONT_DIR / f"{stem}.ttf"
    return path if path.is_file() else None


def _subset(face: str, chars: set[str]) -> Path | None:
    source = _font_file(face)
    if source is None:
        return None
    ordered = "".join(sorted(chars))
    digest = hashlib.sha1(f"{face}:{ordered}".encode()).hexdigest()[:10]
    target = _SUBSET_DIR / f"{face}-{digest}.ttf"
    if target.is_file():
        return target
    try:
        from fontTools import subset

        _SUBSET_DIR.mkdir(parents=True, exist_ok=True)
        opts = subset.Options()
        opts.layout_features = ["kern"]
        opts.notdef_outline = True
        font = subset.load_font(str(source), opts)
        engine = subset.Subsetter(opts)
        engine.populate(text=ordered)
        engine.subset(font)
        tmp = target.with_suffix(".tmp")
        subset.save_font(font, str(tmp), opts)
        tmp.replace(target)
        return target
    except Exception:  # noqa: BLE001
        return None


def _collect_line(page, rec: DropCap, dx: float):
    """找到该段中文首行：字号等于正文、首字是汉字、靠版心左缘、纵向最接近原首行。"""
    best = None
    for line, spans in _spans(page):
        chars = [(ch, span) for span in spans for ch in span.get("chars", []) if ch["c"] != "\n"]
        if len(chars) < 6:
            continue
        first, first_span = chars[0]
        x0, y0, x1, y1 = (float(v) for v in line["bbox"])
        if x0 < dx - 1.0 or not _CJK_RE.match(first["c"]):
            continue
        if abs(float(first_span["size"]) - rec.body_size) > 0.35 or not (rec.col_x0 + dx - 3.0 <= x0 <= rec.col_x0 + dx + 30.0):
            continue
        if not (rec.line_y0 - 10.0 <= y0 <= rec.line_y1 + 4.0):
            continue
        score = abs(y0 - rec.line_y0)
        if best is None or score < best[0]:
            best = (score, line, chars)
    return None if best is None else (best[1], best[2])


def emphasize_zh_first_char(page, rec: DropCap, *, dx: float = 0.0, scale: float | None = None) -> bool:
    """首字加粗放大，其余字符等比收紧到原右缘；任何一步不可行都返回 False 且页面不变。"""
    fitz = _import_fitz()
    scale = scale or zh_scale()
    hit = _collect_line(page, rec, dx)
    if hit is None:
        return False
    line, chars = hit
    x0, y0, x1, y1 = (float(v) for v in line["bbox"])
    first, first_span = chars[0]
    big = float(first_span["size"]) * scale
    plan: list[tuple[str, str, float, float, float, tuple[float, float, float]]] = []  # (face, ch, x, y, size, rgb)
    need: dict[str, set[str]] = {_BOLD_FONT: {first["c"]}}
    for ch, span in chars:
        color = int(span.get("color", 0))
        rgb = (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)
        face = re.sub(r"^[A-Z]{6}\+", "", str(span.get("font") or ""))
        if _font_file(face) is None:
            if ord(ch["c"]) < 128:
                face = _FALLBACK_LATIN
            else:
                return False
        if ch is first:
            face = _BOLD_FONT
        else:
            need.setdefault(face, set()).add(ch["c"])
        plan.append((face, ch["c"], float(ch["origin"][0]), float(ch["origin"][1]), float(span["size"]), rgb))
    files = {face: _subset(face, set(chs) | {" "}) for face, chs in need.items()}
    if any(path is None for path in files.values()):
        return False
    bold_font = fitz.Font(fontfile=str(files[_BOLD_FONT]))
    first_w = float(bold_font.text_length(first["c"], fontsize=big))
    old_first_end = float(first["bbox"][2])
    start = float(first["origin"][0]) + first_w + 0.4
    span_old = x1 - old_first_end
    span_new = x1 - start
    if span_old <= 0 or span_new / span_old < 0.9:
        return False
    ratio = span_new / span_old
    rect = fitz.Rect(x0 - 0.5, y0 + 1.5, x1 + 0.5, y1 - 1.5)
    page.add_redact_annot(rect, fill=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    names: dict[str, str] = {}
    for face, path in files.items():
        names[face] = "qdc" + hashlib.sha1(f"{face}:{path}".encode()).hexdigest()[:8]
        page.insert_font(fontname=names[face], fontfile=str(path))
    for index, (face, text, x, y, size, rgb) in enumerate(plan):
        if index == 0:
            page.insert_text((x, y), text, fontname=names[face], fontsize=big, color=rgb)
            continue
        new_x = start + (x - old_first_end) * ratio
        page.insert_text((new_x, y), text, fontname=names[face], fontsize=size, color=rgb)
    return True


def restore_dual_source_half(page, origin_doc, origin_page: int) -> bool:
    """双语页左半（送翻译的副本）换回原件页。"""
    fitz = _import_fitz()
    half = float(page.rect.width) / 2.0
    if half < 100:
        return False
    left = fitz.Rect(0, 0, half, float(page.rect.height))
    page.draw_rect(left, color=None, fill=(1, 1, 1), width=0)
    page.show_pdf_page(left, origin_doc, origin_page)
    return True


def finish_dropcaps(pdf: Path, origin: Path, records: list[DropCap], *, dual: bool) -> dict[str, Any]:
    """译后处理一份输出 PDF；返回统计。整份文件失败时不改文件。"""
    summary: dict[str, Any] = {"emphasized": 0, "restored": 0, "skipped": 0}
    if not dropcap_enabled() or not records or not pdf.is_file():
        return summary
    fitz = _import_fitz()
    doc = fitz.open(str(pdf))
    origin_doc = fitz.open(str(origin)) if dual and origin.is_file() else None
    try:
        changed = False
        for rec in records:
            if rec.page >= len(doc):
                continue
            page = doc[rec.page]
            dx = float(page.rect.width) / 2.0 if dual else 0.0
            try:
                if emphasize_zh_first_char(page, rec, dx=dx):
                    summary["emphasized"] += 1
                    changed = True
                else:
                    summary["skipped"] += 1
                if dual and origin_doc is not None and restore_dual_source_half(page, origin_doc, rec.page):
                    summary["restored"] += 1
                    changed = True
            except Exception:  # noqa: BLE001
                summary["skipped"] += 1
        if changed:
            tmp = pdf.with_suffix(pdf.suffix + ".dctmp")
            doc.save(str(tmp), garbage=0, deflate=True)
            tmp.replace(pdf)
        return summary
    finally:
        if origin_doc is not None:
            origin_doc.close()
        doc.close()
