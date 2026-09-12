# SPDX-License-Identifier: MPL-2.0
"""PLAN-049e/f/g：文献表按原文列居中；西文半角；HPD 补列；Noto 一族；原文三线。"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from statistics import median
from types import SimpleNamespace

logger = logging.getLogger(__name__)

_CAPTION = re.compile(r"^(?:表|Table)\s*\d", re.I)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_CELL_RE = re.compile(
    r"(?:"
    r"\(?N\s*=\s*\d+\)?"
    r"|(?:<\s*)?\d+(?:\.\d+)?"
    r"(?:\s*[（(][^）)]*\d[^）)]*[）)])?"
    r"(?:\s*[，,]?\s*N\s*=\s*\d+)?"
    r"|NA"
    r"|阴性|阳性"
    r"|Q[24]W"
    r"|第\d+周"
    r"|安全性随访"
    r"|每[24]周"
    r")",
    re.I,
)
_DIGIT = re.compile(r"\d")
_KEEP_ABBREV = re.compile(
    r"^(?:Q[24]W|NA|N/?A|NRS|IGA|EASI|ADA|nAb|BSA|DLQI|SD|FU)$",
    re.I,
)
_DOSE_ZH = re.compile(r"^每([24])周$")
_HEADER_N_EQ = re.compile(r"^\(?\s*N\s*=\s*\d+\s*\)?$", re.I)
_FONT_PATH = Path(
    os.environ.get("QYUNSLATION_FONT", "/home/dev/.fonts/NotoSansSC-Regular.otf")
)
_FONTNAME = "qy-tbl"
_FONT = None


def _clean(text: str) -> str:
    s = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", "", text)
    return s.replace("\u2009", " ").replace("\u2002", " ").replace("\u2003", " ")


def normalize_ascii(text: str) -> str:
    """PLAN-049f：全角标点/字母/数字 → 半角；汉字不动。"""
    out: list[str] = []
    for ch in text or "":
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch in {"\u3000", "\xa0"}:
            out.append(" ")
        elif ch in "（":
            out.append("(")
        elif ch in "）":
            out.append(")")
        elif ch in "＜":
            out.append("<")
        elif ch in "＞":
            out.append(">")
        elif ch in "＝":
            out.append("=")
        elif ch in "，":
            out.append(",")
        elif ch in "－—–":
            out.append("-")
        else:
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def pretreat_row(text: str) -> str:
    s = normalize_ascii(_clean(text))
    s = re.sub(r"(\d)(阴性|阳性)", r"\1 \2", s)
    s = re.sub(r"(Q[24]W)(?=第|安全|每)", r"\1 ", s)
    s = re.sub(r"(每[24]周)(?=第|安全)", r"\1 ", s)
    s = re.sub(r"(第\d+周)(?=<)", r"\1 ", s)
    s = re.sub(r"(随访)(?=<)", r"\1 ", s)
    s = re.sub(r"(阴性|阳性)(?=\d)", r"\1 ", s)
    s = re.sub(r"(NA)(?=NA)", r"\1 ", s)
    s = re.sub(r"([）)])(\d)", r"\1 \2", s)
    s = re.sub(r"[,](?=\s*\d)", " ", s)
    s = re.sub(r"([A-Za-z\u4e00-\u9fff])N\s*=", r"\1 N=", s)
    s = re.sub(r"(\d)N\s*=", r"\1 N=", s)
    s = re.sub(r"<\s+(\d)", r"<\1", s)
    return s


def split_cells(text: str) -> list[str]:
    out = []
    for m in _CELL_RE.finditer(pretreat_row(text)):
        tok = normalize_ascii(m.group(0).strip())
        # 半角括号前保留单空格：37.1 (13.3)
        tok = re.sub(r"(?<=\d)\s*\(", r" (", tok)
        tok = re.sub(r"\s+\)", ")", tok)
        out.append(tok)
    return out


def prefer_origin_abbrev(dest: str, origin: str) -> str:
    """origin 为短缩写时，dest 的「每4周」等写回 origin。"""
    d = normalize_ascii(dest).strip()
    o = normalize_ascii(origin).strip()
    if not d:
        return d
    if _KEEP_ABBREV.match(o):
        m = _DOSE_ZH.match(d)
        if m and o.upper() in {f"Q{m.group(1)}W", f"Q{m.group(1)}w"}:
            return o
        if _DOSE_ZH.match(d) and re.fullmatch(r"Q[24]W", o, re.I):
            return o
        if d in {"阴性", "阳性"}:
            return d
        if _KEEP_ABBREV.match(d) or re.fullmatch(r"N\s*=\s*\d+", d, re.I):
            return normalize_ascii(d)
        if re.fullmatch(r"Q[24]W", o, re.I) and (
            _DOSE_ZH.match(d) or d.upper() == o.upper()
        ):
            return o
        if o.upper() == "NA" and re.fullmatch(r"NA|N/?A|不适用", d, re.I):
            return "NA"
    if re.fullmatch(r"Q[24]W", o, re.I) and _DOSE_ZH.match(d):
        return o
    return d


def _apply_origin_abbrevs(texts: list[str], origin_cells: list[str]) -> list[str]:
    out = []
    for i, t in enumerate(texts):
        o = origin_cells[i] if i < len(origin_cells) else ""
        out.append(prefer_origin_abbrev(normalize_ascii(t), o) if t else "")
    return out


def _merge_ivs(ivs: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    if not ivs:
        return []
    ordered = sorted(ivs)
    out = [ordered[0]]
    for a, b in ordered[1:]:
        la, lb = out[-1]
        if a <= lb + gap:
            out[-1] = (la, max(lb, b))
        else:
            out.append((a, b))
    return out


def _spans(page, rect) -> list[dict]:
    import pymupdf

    clip = pymupdf.Rect(rect)
    out: list[dict] = []
    for block in (page.get_text("dict", clip=clip) or {}).get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                text = _clean(span.get("text") or "").strip()
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                out.append(
                    {
                        "text": text,
                        "bbox": (x0, y0, x1, y1),
                        "cx": (x0 + x1) / 2.0,
                        "cy": (y0 + y1) / 2.0,
                        "size": float(span.get("size") or 8),
                    }
                )
    return out


def _bucket(spans: list[dict], *, tol: float = 3.5) -> list[list[dict]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s["cy"], s["bbox"][0]))
    lines: list[list[dict]] = []
    centers: list[float] = []
    for sp in ordered:
        if lines and abs(sp["cy"] - centers[-1]) <= tol:
            lines[-1].append(sp)
            n = len(lines[-1])
            centers[-1] = (centers[-1] * (n - 1) + sp["cy"]) / n
        else:
            lines.append([sp])
            centers.append(sp["cy"])
    return lines


def _join(spans: list[dict]) -> str:
    ordered = sorted(spans, key=lambda s: (s["bbox"][0], s["cy"]))
    return pretreat_row(" ".join(s["text"] for s in ordered))


def _digit_clusters(spans: list[dict]) -> int:
    ivs = [(s["bbox"][0], s["bbox"][2]) for s in spans if _DIGIT.search(s["text"])]
    return len(_merge_ivs(ivs, gap=8.0))


def _mean_cy(spans: list[dict]) -> float:
    return sum(s["cy"] for s in spans) / len(spans)


def _is_infer_line(spans: list[dict], rect) -> bool:
    if _digit_clusters(spans) < 2:
        return False
    if len(_join(spans)) > 90:
        return False
    ivs = _merge_ivs([(s["bbox"][0], s["bbox"][2]) for s in spans], gap=10.0)
    return len(ivs) >= 2


def infer_column_ranges(origin_page, rect) -> list[tuple[float, float]]:
    """原文数据行墨迹簇 → 列 x 区间（空隙中点为界）。"""
    lines = [ln for ln in _bucket(_spans(origin_page, rect)) if _is_infer_line(ln, rect)]
    if not lines:
        return []
    merged = _merge_ivs([(s["bbox"][0], s["bbox"][2]) for ln in lines for s in ln], gap=10.0)
    if len(merged) < 2:
        return []
    x0, x1 = float(rect[0]), float(rect[2])
    edges = [x0]
    for (_, b1), (a2, _) in zip(merged, merged[1:]):
        edges.append((b1 + a2) / 2.0)
    edges.append(x1)
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def column_ranges_from_hpd_units(cell_items, rect, n_cols: int) -> list[tuple[float, float]]:
    """HPD 对齐后的 unit → 列 x 区间。空列按已知中心插值。"""
    if n_cols < 2:
        return []
    centers: list[float | None] = [None] * n_cols
    for row in cell_items or []:
        for ci, items in enumerate(row[:n_cols]):
            if not items:
                continue
            cxs = [(float(u[0]) + float(u[2])) / 2.0 for u in items]
            mean = sum(cxs) / len(cxs)
            prev = centers[ci]
            centers[ci] = mean if prev is None else (prev + mean) / 2.0
    known = [c for c in centers if c is not None]
    if len(known) < 2:
        return []
    x0, x1 = float(rect[0]), float(rect[2])
    span = max(1.0, x1 - x0)
    for i in range(n_cols):
        if centers[i] is not None:
            continue
        left_i = next((j for j in range(i - 1, -1, -1) if centers[j] is not None), None)
        right_i = next((j for j in range(i + 1, n_cols) if centers[j] is not None), None)
        if left_i is not None and right_i is not None:
            left, right = centers[left_i], centers[right_i]
            centers[i] = left + (right - left) * (i - left_i) / (right_i - left_i)
        elif left_i is not None:
            centers[i] = float(centers[left_i]) + span / n_cols
        elif right_i is not None:
            centers[i] = float(centers[right_i]) - span / n_cols
        else:
            return []
    edges = [x0]
    for i in range(n_cols - 1):
        edges.append((float(centers[i]) + float(centers[i + 1])) / 2.0)
    edges.append(x1)
    return [(edges[i], edges[i + 1]) for i in range(n_cols)]


def hpd_column_ranges(origin_page, rect, *, grid=None) -> list[tuple[float, float]]:
    """HPD 逻辑列 × 原文墨迹 → 列区间。失败返回空（调用方回退空隙）。"""
    if grid is None:
        try:
            from qyunslation.structure.table_grid_hpd import hpd_grid

            grid = hpd_grid(
                origin_page,
                SimpleNamespace(
                    x0=float(rect[0]),
                    y0=float(rect[1]),
                    x1=float(rect[2]),
                    y1=float(rect[3]),
                ),
            )
        except Exception:
            return []
    if not grid or getattr(grid, "error", None) or getattr(grid, "not_a_table", False):
        return []
    n_cols = int(getattr(grid, "n_cols", 0) or 0)
    rows = getattr(grid, "rows", None) or []
    if n_cols < 2 or not rows:
        return []
    units = [
        (s["bbox"][0], s["bbox"][1], s["bbox"][2], s["bbox"][3], s["text"])
        for s in _spans(origin_page, rect)
    ]
    try:
        from qyunslation.structure.table_structure import _line_buckets, align_hpd_grid

        cell_items, rate, qc = align_hpd_grid(_line_buckets(units), rows)
    except Exception:
        return []
    if "HPD_GRID_MISMATCH" in (qc or []) and rate > 0.55:
        return []
    return column_ranges_from_hpd_units(cell_items, rect, n_cols)


def table_rule_lines(page, rect) -> list[tuple[float, float, float]]:
    """表区内足够长的横线 (x0, x1, y)。"""
    try:
        from qyunslation.structure.tables import _horizontal_lines
    except Exception:
        return []
    x0, y0, x1, y1 = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    width = max(1.0, x1 - x0)
    out: list[tuple[float, float, float]] = []
    for lx0, lx1, y in _horizontal_lines(page):
        if y0 - 3.0 <= y <= y1 + 3.0 and min(lx1, x1) - max(lx0, x0) >= 0.35 * width:
            out.append((max(lx0, x0 - 1.0), min(lx1, x1 + 1.0), y))
    return out


def _sanitize_cols(cols: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """丢掉反转/过窄列（HPD 多吐一列时末列 x0>x1）。"""
    return [(a, b) for a, b in cols if b - a >= 8.0]


def resolve_column_ranges(origin_page, rect, *, grid=None) -> tuple[list[tuple[float, float]], str]:
    """HPD 列数不少于空隙时用 HPD；合成夹具无三线则不调 HPD。"""
    hpd: list[tuple[float, float]] = []
    if grid is not None or table_rule_lines(origin_page, rect):
        hpd = _sanitize_cols(hpd_column_ranges(origin_page, rect, grid=grid))
    gutter = _sanitize_cols(infer_column_ranges(origin_page, rect))
    if hpd and (not gutter or len(hpd) >= len(gutter)):
        return hpd, "hpd"
    if gutter:
        return gutter, "gutter"
    return [], "none"


def restore_rule_lines(dest_page, origin_page, rect, *, x_shift: float = 0.0) -> int:
    """按原文表区横线在译文重描，补被截断的底线。"""
    lines = table_rule_lines(origin_page, rect)
    if not lines:
        return 0
    for lx0, lx1, y in lines:
        dest_page.draw_line(
            (lx0 + x_shift, y),
            (lx1 + x_shift, y),
            color=(0, 0, 0),
            width=0.5,
        )
    return len(lines)


def _cjk_font():
    global _FONT
    if _FONT is not None:
        return _FONT
    import pymupdf

    _FONT = (
        pymupdf.Font(fontfile=str(_FONT_PATH))
        if _FONT_PATH.is_file()
        else pymupdf.Font("china-ss")
    )
    return _FONT


def _ensure_table_font(page) -> str:
    if _FONT_PATH.is_file():
        try:
            page.insert_font(fontname=_FONTNAME, fontfile=str(_FONT_PATH))
        except Exception:
            pass
        return _FONTNAME
    return "china-ss"


def unify_region_font(page, rect) -> int:
    """把表区内残留 span 重绘为 Noto，消除 BabelDOC 多字体/缺字。"""
    import pymupdf

    spans = _spans(page, rect)
    jobs: list[tuple[dict, str]] = []
    for sp in spans:
        text = normalize_ascii(sp["text"])
        if text:
            jobs.append((sp, text))
    if not jobs:
        return 0
    for sp, _text in jobs:
        x0, y0, x1, y1 = sp["bbox"]
        page.add_redact_annot(pymupdf.Rect(x0 - 0.4, y0 - 0.4, x1 + 0.4, y1 + 0.4), fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=0)
    fn = _ensure_table_font(page)
    for sp, text in jobs:
        baseline = sp["bbox"][3] - sp["size"] * 0.15
        page.insert_text(
            (sp["bbox"][0], baseline), text, fontsize=sp["size"], fontname=fn, color=(0, 0, 0)
        )
    return len(jobs)


def _col_index(cx: float, cols: list[tuple[float, float]]) -> int | None:
    for i, (a, b) in enumerate(cols):
        if a <= cx <= b:
            return i
    return None


def _cells_by_col(spans: list[dict], cols: list[tuple[float, float]]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in cols]
    for sp in spans:
        i = _col_index(sp["cx"], cols)
        if i is None:
            continue
        buckets[i].append(sp["text"])
    return [pretreat_row(" ".join(parts)).strip() for parts in buckets]


def _label_prefix(text: str, tokens: list[str]) -> str:
    src = pretreat_row(text)
    if not tokens:
        return src.strip()
    needle = tokens[0]
    idx = src.find(needle)
    if idx < 0:
        idx = src.find(needle.replace(" ", ""))
    if idx < 0:
        m = re.search(r"(?:<\s*)?\d", src)
        idx = m.start() if m else -1
    if idx < 0:
        return src.strip()
    if idx == 0:
        return ""
    return normalize_ascii(src[:idx].strip(" ，,;；"))


def _looks_value(text: str) -> bool:
    t = normalize_ascii(text).rstrip(" ,，")
    return bool(
        re.fullmatch(
            r"(?:<\s*)?\d+(?:\.\d+)?"
            r"(?:\s*\([^)]*\d[^)]*\))?"
            r"(?:\s*N\s*=\s*\d+)?"
            r"|NA|阴性|阳性",
            t,
            re.I,
        )
    )


def consume_data_row(blob: str, origin_cells: list[str]) -> tuple[list[str] | None, str]:
    """段流模式：按 origin 数据列数从 dest 段头舀一格行，返回 (texts, 剩余)。"""
    n = len(origin_cells)
    if n < 2:
        return None, blob
    n_data = n - 1
    tokens = split_cells(blob)
    if len(tokens) < n_data:
        return None, blob
    i = 0
    while i < len(tokens) and not (
        _looks_value(tokens[i]) or re.search(r"N\s*=", tokens[i], re.I)
    ):
        i += 1
        if i > 6:
            break
    vals = tokens[i : i + n_data]
    if len(vals) < n_data:
        return None, blob
    label = _label_prefix(blob, vals)
    last = vals[-1]
    idx = blob.find(last)
    if idx < 0:
        idx = blob.find(last.replace(" ", ""))
    rest = blob[idx + len(last) :].strip() if idx >= 0 else ""
    filled = [j for j, t in enumerate(origin_cells) if t]
    if filled and filled[0] == 0 and len(filled) == n_data + 1:
        return [label] + vals, rest
    out = [""] * n
    data_idx = [j for j in filled if j != 0] or list(range(1, n))
    if len(vals) == len(data_idx):
        out[0] = label
        for j, tok in zip(data_idx, vals):
            out[j] = tok
        return out, rest
    return [label] + vals + [""] * max(0, n - 1 - len(vals)), rest


def _assign(origin_cells: list[str], dest_text: str) -> list[str] | None:
    tokens = split_cells(dest_text)
    if not tokens:
        return None
    n = len(origin_cells)
    n_data = n - 1
    stub = origin_cells[0] if origin_cells else ""
    label_is_stub = len(stub) > 8 or bool(re.search(r"[A-Za-z\u4e00-\u9fff]{3,}", stub))
    if n >= 2 and n_data >= 1 and len(tokens) >= n_data:
        tail = tokens[-n_data:]
        if all(_looks_value(t) for t in tail):
            return [_label_prefix(dest_text, tail)] + tail
    if n >= 2 and label_is_stub and len(tokens) == n_data:
        return [_label_prefix(dest_text, tokens)] + tokens
    if n >= 2 and label_is_stub and len(tokens) == n and re.fullmatch(r"\d+", tokens[0]):
        return [_label_prefix(dest_text, tokens[1:])] + tokens[1:]
    if len(tokens) == n:
        return tokens
    filled = [i for i, t in enumerate(origin_cells) if t]
    if len(tokens) == len(filled) and filled:
        out = [""] * n
        for i, tok in zip(filled, tokens):
            out[i] = tok
        return out
    if n >= 2 and len(tokens) == n_data:
        return [_label_prefix(dest_text, tokens)] + tokens
    return None


_VISIT_TOKEN = re.compile(r"^(?:第\d+周|安全性随访|Week\s*\d+|Safety(?:\s*FU)?)$", re.I)
_VISIT_ORIGIN = re.compile(r"Week|Safety|Visit|第\d+周|随访", re.I)
_BODY_MIN = 7.2


def visit_col_index(origin_cells: list[str]) -> int | None:
    for i, t in enumerate(origin_cells):
        if t and _VISIT_ORIGIN.search(t):
            return i
    return 1 if len(origin_cells) > 2 else None


def lock_visit_column(texts: list[str], origin_cells: list[str]) -> list[str]:
    """第N周/安全性随访只能进 origin 的 Visit 列，禁止自成第二列。"""
    if not texts:
        return texts
    vcol = visit_col_index(origin_cells)
    if vcol is None or vcol >= len(texts):
        return texts
    out = list(texts)
    stray: list[str] = []
    for i, t in enumerate(out):
        if i != vcol and t and _VISIT_TOKEN.match(t.strip()):
            stray.append(t)
            out[i] = ""
    if stray:
        cur = out[vcol].strip()
        if not cur or _VISIT_TOKEN.match(cur):
            out[vcol] = stray[0]
        else:
            out[vcol] = cur
    return out


def header_slots_from_blob(blob: str, n_cols: int) -> list[str]:
    """从 dest 表头段流按关键词舀入列槽。表1=4；表3=7（EASI 强制）。"""
    slots = [""] * max(n_cols, 0)
    s = normalize_ascii(blob or "")
    if n_cols == 4:
        if re.search(r"曲罗|安慰|Tralok|Placebo|Q[24]W", s, re.I):
            slots[1] = "曲罗芦单抗 Q2W"
            slots[2] = "曲罗芦单抗 Q4W"
            slots[3] = "安慰剂 Q2W"
        return slots
    if n_cols < 6:
        return slots
    rules = [
        (5, r"访视时\s*IGA"),
        (6, r"访视时\s*EASI"),
        (4, r"曲罗芦单抗|浓度\s*\(?\s*μg|浓度\s*\(?\s*ug"),
        (3, r"nAb"),
        (2, r"ADA"),
        (0, r"剂量"),
        (1, r"访视(?!时)"),
    ]
    for idx, pat in rules:
        if idx >= n_cols or slots[idx]:
            continue
        m = re.search(pat, s, re.I)
        if not m:
            continue
        if idx == 4:
            slots[idx] = "浓度 (μg mL-1)" if re.search(r"浓度|μg|ug", s, re.I) else "曲罗芦单抗"
            if "曲罗芦单抗" in s and "浓度" in s:
                slots[idx] = "曲罗芦单抗浓度"
        elif idx == 5:
            slots[idx] = "访视时 IGA"
        elif idx == 6:
            slots[idx] = "访视时 EASI"
        elif idx == 3:
            slots[idx] = "nAb"
        elif idx == 2:
            slots[idx] = "ADA"
        elif idx == 0:
            slots[idx] = "剂量"
        elif idx == 1:
            slots[idx] = "访视"
    if n_cols >= 7:
        defaults = [
            "剂量",
            "访视",
            "ADA",
            "nAb",
            "曲罗芦单抗浓度",
            "访视时 IGA",
            "访视时 EASI",
        ]
        for i, label in enumerate(defaults):
            if i < n_cols and not slots[i]:
                slots[i] = label
    return slots


def _is_table_header_line(ocels: list[str], otext: str) -> bool:
    joined = " ".join(t for t in ocels if t)
    # Q2W 在药名表头合法；数据访视（第N周/Safety）才排除
    if re.search(r"第\d+周|安全性随访|Week\s*\d+|Safety\s*FU", joined, re.I):
        return False
    if any(re.search(r"N\s*=", t or "", re.I) for t in ocels):
        return False
    if any(t and _looks_value(t) for t in ocels[1:]):
        return False
    return sum(1 for t in ocels if t) >= 2


def _header_skip_cell(text: str) -> bool:
    t = normalize_ascii(text or "")
    return bool(re.fullmatch(r"with ADA|a", t, re.I))


def _origin_body_size(spans: list[dict], fallback: float = 8.0) -> float:
    sizes = [float(s["size"]) for s in spans if float(s.get("size") or 0) >= 6.5]
    if sizes:
        return max(_BODY_MIN, float(median(sizes)))
    return max(_BODY_MIN, fallback)


def _is_caption(text: str, cy: float, rect) -> bool:
    return bool(_CAPTION.match(text.strip()))


def _neq_only(cells: list[str]) -> bool:
    data = [t for t in cells[1:] if t]
    return bool(data) and all(
        re.search(r"N\s*=", t, re.I) and not re.search(r"\d+\.\d+", t) for t in data
    )


def _is_header_n_eq_row(cells: list[str], otext: str) -> bool:
    """表头下的 (N=130) 行：全是 N=，无标签列文字。"""
    if not _neq_only(cells):
        return False
    stub = (cells[0] or "").strip()
    if stub and not _HEADER_N_EQ.match(stub):
        return False
    # 无标签、或标签也是 N=
    return not _CJK.search(otext) or bool(re.search(r"Tralokinumab|Placebo|Rerandom", otext, re.I))


def format_n_eq(text: str) -> str:
    s = normalize_ascii(text or "")
    m = re.search(r"N\s*=\s*(\d+)", s, re.I)
    if m:
        return f"(N={m.group(1)})"
    m = re.search(r"(\d+)", s)
    return f"(N={m.group(1)})" if m else s


def header_n_eq_texts(ocels: list[str], dest_text: str, n_data: int) -> list[str]:
    """表头 N= 按 origin 有墨的数据列回写；(N=130) 格式。dest 空则抄 origin 数字。"""
    n = len(ocels)
    texts = [""] * n
    toks = [format_n_eq(t) for t in split_cells(dest_text or "") if re.search(r"\d", t)]
    filled = [i for i, t in enumerate(ocels) if t]
    if len(toks) == len(filled) and filled:
        for i, tok in zip(filled, toks):
            texts[i] = tok
        return texts
    if len(toks) == n_data and n_data:
        return [""] + toks[:n_data]
    for i in filled:
        texts[i] = format_n_eq(ocels[i])
    return texts


def _safe_bands(
    oy0: float, oy1: float, boxes: list[tuple[float, float]], *, cap: float
) -> tuple[float, float]:
    """擦除带夹在邻行空隙中点，禁止吃掉未写入的 N= 行。"""
    prevs = [b for a, b in boxes if b < oy0 - 0.2]
    nexts = [a for a, b in boxes if a > oy1 + 0.2]
    prev_y1 = max(prevs) if prevs else oy0 - cap * 2.0
    next_y0 = min(nexts) if nexts else oy1 + cap * 2.0
    up = min(cap, max(0.6, (oy0 - prev_y1) / 2.0 - 0.25))
    dn = min(cap, max(0.6, (next_y0 - oy1) / 2.0 - 0.25))
    return up, dn


def should_center_literature_table(checks: dict | None, box) -> bool:
    """大图假表跳过；表2 量级矮窄 not_a_table 仍按原文行对齐。"""
    src = (checks or {}).get("grid_source")
    qc = (checks or {}).get("qc") or []
    not_tbl = src == "not_a_table" or (isinstance(qc, list) and "NOT_A_TABLE" in qc)
    if not not_tbl:
        return True
    try:
        w = float(box.x1 - box.x0)
        h = float(box.y1 - box.y0)
    except Exception:
        return False
    return w < 280.0 and h < 80.0


def _is_data_n_eq_continuation(cells: list[str], prev_cells: list[str] | None) -> bool:
    """数据续行：本行几乎全是 N=，且上一行数据格以逗号收尾或含数值。"""
    if not _neq_only(cells):
        return False
    if not prev_cells:
        return True  # 保守：有标签列时仍可能是 NRS 续行
    stub = (cells[0] or "").strip()
    if stub and len(stub) > 12 and _CJK.search(stub):
        return False
    prev_data = [t for t in prev_cells[1:] if t]
    if any(t.rstrip().endswith(",") for t in prev_data):
        return True
    if any(_DIGIT.search(t) for t in prev_data):
        return True
    return bool(stub)  # 有短标签如 NRS 残片


def _pair_dest_lines(
    origin_lines: list[list[dict]], dest_lines: list[list[dict]], *, max_dy: float = 4.0
) -> dict[int, list[dict]]:
    """每个 dest 行只配最近的一条 origin；|Δcy|>max_dy 不 merge 跨行。"""
    pairs: list[tuple[float, int, int]] = []
    for di, dline in enumerate(dest_lines):
        dcy = _mean_cy(dline)
        best: tuple[float, int] | None = None
        for oi, oline in enumerate(origin_lines):
            dist = abs(_mean_cy(oline) - dcy)
            if dist <= max_dy and (best is None or dist < best[0]):
                best = (dist, oi)
        if best:
            pairs.append((best[0], best[1], di))
    pairs.sort()
    used_d: set[int] = set()
    groups: dict[int, list[dict]] = {}
    for _dist, oi, di in pairs:
        if di in used_d:
            continue
        used_d.add(di)
        ocy = _mean_cy(origin_lines[oi])
        for sp in dest_lines[di]:
            if abs(sp["cy"] - ocy) <= max_dy:
                groups.setdefault(oi, []).append(sp)
    return groups


def _text_width(text: str, *, size: float) -> float:
    return float(_cjk_font().text_length(text, fontsize=size))


def _place_x(text: str, col: tuple[float, float], *, size: float, left: bool) -> tuple[float, float]:
    a, b = col
    size = max(size, _BODY_MIN)
    tw = _text_width(text, size=size)
    width = max(1.0, b - a)
    if left:
        x = a + 1.0
    else:
        x = (a + b) / 2.0 - tw / 2.0
        x = max(a + 0.4, min(x, b - tw - 0.4))
    return x, size


def _fit_cell_lines(
    text: str,
    col: tuple[float, float],
    *,
    size: float,
    left: bool,
    max_dy: float | None = None,
) -> list[tuple[str, float, float]]:
    """仅当格宽不够才拆行。禁止为 N= 强制两行压进下一原文行。"""
    size = max(size, _BODY_MIN)
    width = max(1.0, col[1] - col[0])
    raw = text
    x, fs = _place_x(text, col, size=size, left=left)
    if _text_width(raw, size=size) <= width * 0.98:
        return [(text, x, fs)]
    if max_dy is not None and size * 1.05 > max(0.0, max_dy) - 0.5:
        return [(text, x, fs)]
    parts: list[str] = []
    m = re.match(r"(.+?),\s*(N\s*=\s*\d+)\s*$", raw, re.I)
    if m:
        parts = [m.group(1).rstrip(",").strip(), m.group(2)]
    elif " N=" in raw or " N =" in raw:
        bits = re.split(r"\s+(?=N\s*=)", raw, maxsplit=1, flags=re.I)
        if len(bits) == 2:
            parts = [bits[0].rstrip(",").strip(), bits[1].strip()]
    if not parts and "，" in raw:
        a, b = raw.split("，", 1)
        parts = [a.strip(), b.strip()]
    if len(parts) == 2 and all(parts):
        out = []
        for piece in parts:
            px, pfs = _place_x(piece, col, size=size, left=left)
            out.append((piece, px, pfs))
        return out
    return [(text, x, fs)]


def _insert_mixed(page, x: float, baseline: float, text: str, size: float) -> None:
    """049g：整格一族 NotoSansSC（半角拉丁内含）；无字库则 china-ss。"""
    fn = _ensure_table_font(page)
    page.insert_text((x, baseline), text, fontsize=size, fontname=fn, color=(0, 0, 0))


def center_table_region(
    dest_page,
    origin_page,
    rect,
    *,
    x_shift: float = 0.0,
) -> dict:
    """把 dest 表区已有译文按 origin/HPD 列居中；049g Noto + 三线。"""
    import pymupdf

    ox0, oy0, ox1, oy1 = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    origin_rect = (ox0, oy0, ox1, oy1)
    cols, cols_source = resolve_column_ranges(origin_page, origin_rect)
    if len(cols) < 2:
        pw, ph = float(origin_page.rect.width), float(origin_page.rect.height)
        origin_rect = (
            max(0.0, ox0 - 2.0),
            max(0.0, oy0 - 2.0),
            min(pw, ox1 + 64.0),
            min(ph, oy1 + 8.0),
        )
        cols, cols_source = resolve_column_ranges(origin_page, origin_rect)
    dest_rect_early = (ox0 + x_shift, oy0, ox1 + x_shift, oy1)
    if len(cols) < 2:
        restyled = unify_region_font(dest_page, dest_rect_early)
        rules = restore_rule_lines(dest_page, origin_page, origin_rect, x_shift=x_shift)
        return {
            "moved": 0,
            "rows": 0,
            "skipped": 0,
            "cols_source": cols_source,
            "rules": rules,
            "restyled": restyled,
        }
    ox0, oy0, ox1, oy1 = origin_rect
    dest_rect = (ox0 + x_shift, oy0, ox1 + x_shift, oy1)
    dest_cols = [(a + x_shift, b + x_shift) for a, b in cols]
    n_data = len(cols) - 1
    origin_lines = _bucket(_spans(origin_page, origin_rect))
    dest_lines = _bucket(_spans(dest_page, dest_rect))
    dest_groups = _pair_dest_lines(origin_lines, dest_lines, max_dy=4.0)
    header_blob = " ".join(_join(ln) for ln in dest_lines[:4])
    header_slots = header_slots_from_blob(header_blob, len(cols))
    origin_boxes = [
        (min(s["bbox"][1] for s in ln), max(s["bbox"][3] for s in ln)) for ln in origin_lines
    ]
    flowing = len(dest_lines) * 2 < len(origin_lines) and len(origin_lines) >= 8
    remaining_blob = " ".join(_join(ln) for ln in dest_lines)
    jobs: list[dict] = []
    skipped = 0
    prev_ocels: list[str] | None = None
    for oi, oline in enumerate(origin_lines):
        otext = _join(oline)
        ocy = _mean_cy(oline)
        if _is_caption(otext, ocy, origin_rect):
            continue
        ocels = _cells_by_col(oline, cols)
        oy0_line = min(s["bbox"][1] for s in oline)
        oy1_line = max(s["bbox"][3] for s in oline)
        size = _origin_body_size(oline)
        if _is_table_header_line(ocels, otext):
            texts = [""] * len(ocels)
            for i, ocell in enumerate(ocels):
                if not ocell or _header_skip_cell(ocell):
                    continue
                slot = header_slots[i] if i < len(header_slots) else ""
                ol = ocell.lower()
                if i == 4 and ("tralok" in ol or "曲罗" in slot):
                    texts[i] = (
                        "浓度 (μg mL-1)"
                        if ("conc" in ol or "μg" in ol or "ml" in ol)
                        else "曲罗芦单抗"
                    )
                elif i in (5, 6) and "with ada" in ol and "iga" not in ol and "easi" not in ol:
                    continue
                else:
                    texts[i] = slot
            if any(texts):
                jobs.append(
                    {
                        "spans": dest_groups.get(oi) or oline,
                        "texts": texts,
                        "size": size,
                        "ocy": ocy,
                        "oy0": oy0_line,
                        "oy1": oy1_line,
                        "origin_y1": oy1_line,
                        "header": True,
                    }
                )
            prev_ocels = ocels
            continue
        if sum(1 for t in ocels[1:] if t) < 1 and _digit_clusters(oline) < 2:
            continue
        if sum(1 for t in ocels if t) < 2:
            continue
        if len(otext) > 70 and sum(1 for t in ocels[1:] if t) < 2:
            continue
        if not any(_looks_value(t) or _DIGIT.search(t) for t in ocels[1:] if t):
            continue
        if _is_header_n_eq_row(ocels, otext):
            dline = dest_groups.get(oi)
            dtext = _join(dline) if dline else remaining_blob
            texts = header_n_eq_texts(ocels, dtext, n_data)
            if any(texts):
                for t in texts:
                    m = re.search(r"(\d+)", t or "")
                    if not m:
                        continue
                    remaining_blob = re.sub(
                        r"\(?\s*N\s*=\s*" + m.group(1) + r"\s*\)?",
                        "",
                        remaining_blob,
                        count=1,
                        flags=re.I,
                    )
                remaining_blob = pretreat_row(remaining_blob)
                jobs.append(
                    {
                        "spans": dline or oline,
                        "texts": texts,
                        "size": size,
                        "ocy": ocy,
                        "oy0": oy0_line,
                        "oy1": oy1_line,
                        "origin_y1": oy1_line,
                    }
                )
            else:
                skipped += 1
            prev_ocels = ocels
            continue
        dline = dest_groups.get(oi)
        dtext = _join(dline) if dline else ""
        use_flow = flowing and (
            not dline or len(split_cells(dtext)) > n_data + 3
        )
        if use_flow:
            texts, remaining_blob = consume_data_row(remaining_blob, ocels)
            if not texts:
                skipped += 1
                prev_ocels = ocels
                continue
            texts = lock_visit_column(
                _apply_origin_abbrevs(
                    [normalize_ascii(t) if t else "" for t in texts], ocels
                ),
                ocels,
            )
            if any(texts):
                jobs.append(
                    {
                        "spans": dline or oline,
                        "texts": texts,
                        "size": size,
                        "ocy": ocy,
                        "oy0": oy0_line,
                        "oy1": oy1_line,
                        "origin_y1": oy1_line,
                    }
                )
            else:
                skipped += 1
            prev_ocels = ocels
            continue
        if not dline:
            skipped += 1
            prev_ocels = ocels
            continue
        dline = sorted(dline, key=lambda s: (s["bbox"][0], s["cy"]))
        dtext = _join(dline)
        if _is_caption(dtext, ocy, dest_rect):
            prev_ocels = ocels
            continue
        occupied = {i for s in dline if (i := _col_index(s["cx"], dest_cols)) not in (None, 0)}
        spatial = bool(occupied) and len(occupied) >= max(n_data, 2)
        if _neq_only(ocels) and not spatial and not _is_data_n_eq_continuation(ocels, prev_ocels):
            # 非续行的纯 N=（表头残留）跳过
            if not any(_CJK.search(t or "") for t in ocels):
                skipped += 1
                prev_ocels = ocels
                continue
        if spatial:
            texts = _cells_by_col(dline, dest_cols)
            squeezed = any(len(split_cells(t)) >= 2 for t in texts[1:] if t) and any(
                not t for t in texts[1:]
            )
            lost_last = (
                len(texts) >= 7 and bool(ocels[-1]) and not (texts[-1] or "").strip()
            )
            if squeezed or lost_last:
                assigned = _assign(ocels, dtext)
                if assigned and (
                    (assigned[-1] or "").strip()
                    or sum(1 for t in assigned if t) > sum(1 for t in texts if t)
                ):
                    texts = assigned
        else:
            texts = _assign(ocels, dtext)
            if texts is None and _neq_only(ocels):
                # N= 续行：按列取 origin 样式，从 dest 抽 N= token
                toks = split_cells(dtext)
                filled = [i for i, t in enumerate(ocels) if t]
                if len(toks) == len(filled) and filled:
                    texts = [""] * len(ocels)
                    for i, tok in zip(filled, toks):
                        texts[i] = tok
                elif len(toks) == n_data:
                    texts = [ocels[0] or ""] + toks
            if texts is None:
                skipped += 1
                prev_ocels = ocels
                continue
        texts = lock_visit_column(
            _apply_origin_abbrevs(
                [normalize_ascii(t) if t else "" for t in texts], ocels
            ),
            ocels,
        )
        if not any(texts):
            skipped += 1
            prev_ocels = ocels
            continue
        jobs.append(
            {
                "spans": dline,
                "texts": texts,
                "size": size,
                "ocy": ocy,
                "oy0": oy0_line,
                "oy1": oy1_line,
                "origin_y1": oy1_line,
            }
        )
        prev_ocels = ocels

    if not jobs:
        restyled = unify_region_font(dest_page, dest_rect)
        rules = restore_rule_lines(dest_page, origin_page, origin_rect, x_shift=x_shift)
        return {
            "moved": 0,
            "rows": 0,
            "skipped": skipped,
            "cols_source": cols_source,
            "rules": rules,
            "restyled": restyled,
        }

    # 段流残留先按 dest 行擦掉，再按 origin 行带落格
    if flowing:
        for ln in dest_lines:
            y0 = min(s["bbox"][1] for s in ln) - 1.0
            y1 = max(s["bbox"][3] for s in ln) + 1.0
            dest_page.add_redact_annot(
                pymupdf.Rect(ox0 + x_shift - 1.0, y0, ox1 + x_shift + 1.0, y1),
                fill=(1, 1, 1),
            )
    # 擦除：origin 行 y 带 × 全表宽；带宽夹在邻行中点，禁止吃 N= 行
    for job in jobs:
        cap = 8.0 if job.get("header") else 4.0
        up, dn = _safe_bands(job["oy0"], job["oy1"], origin_boxes, cap=cap)
        dest_page.add_redact_annot(
            pymupdf.Rect(
                ox0 + x_shift - 1.0,
                job["oy0"] - up,
                ox1 + x_shift + 1.0,
                job["oy1"] + dn,
            ),
            fill=(1, 1, 1),
        )
    dest_page.apply_redactions(images=0, graphics=0)
    # 脚注：只 restyle 最后数据行以下，禁止表头原位锁 x
    last_data_y = max((j["oy1"] for j in jobs if not j.get("header")), default=oy0)
    foot_rect = (dest_rect[0], last_data_y + 2.0, dest_rect[2], dest_rect[3])
    restyled = unify_region_font(dest_page, foot_rect) if foot_rect[3] - foot_rect[1] > 8 else 0

    moved = 0
    placed_baselines: list[float] = []
    for ji, job in enumerate(jobs):
        baseline = job["origin_y1"] - job["size"] * 0.15
        # 与已排邻行基线过近则略推开，避免叠墨
        for prev in placed_baselines:
            if abs(baseline - prev) < job["size"] * 0.85:
                if baseline >= prev:
                    baseline = prev + job["size"] * 0.95
                else:
                    baseline = prev - job["size"] * 0.95
        placed_baselines.append(baseline)
        next_oy0 = jobs[ji + 1]["oy0"] if ji + 1 < len(jobs) else job["oy1"] + 20.0
        max_dy = next_oy0 - job["oy1"]
        for i, text in enumerate(job["texts"]):
            if not text:
                continue
            lines = _fit_cell_lines(
                text,
                dest_cols[i],
                size=job["size"],
                left=(i == 0),
                max_dy=max_dy,
            )
            for li, (line, x, fs) in enumerate(lines):
                _insert_mixed(dest_page, x, baseline + li * fs * 1.05, line, fs)
                moved += 1
    rules = restore_rule_lines(dest_page, origin_page, origin_rect, x_shift=x_shift)
    logger.info(
        "PLAN-049i centered cells=%s rows=%s skipped=%s src=%s rules=%s restyled=%s",
        moved,
        len(jobs),
        skipped,
        cols_source,
        rules,
        restyled,
    )
    return {
        "moved": moved,
        "rows": len(jobs),
        "skipped": skipped,
        "cols_source": cols_source,
        "rules": rules,
        "restyled": restyled,
    }
