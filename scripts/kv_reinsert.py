#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""译后按 OCR kv 盒重绘会议信息表，避免 BabelDOC 串行/缩字。"""
from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "glossaries" / "proper-nouns.csv"


def _load_glossary(path: Path = GLOSSARY) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt:
                rows.append((src, tgt))
    rows.sort(key=lambda it: len(it[0]), reverse=True)
    return rows


def _cjk_glue(text: str) -> str:
    """去掉汉字之间被 OCR/排版塞进的空格（问 题 → 问题）。"""
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text or "")
    return _AGENCY_TAIL_RE.sub("", t).strip()


def _wrap_height(text: str, width: float, fs: float, *, lead: float = 1.42) -> float:
    """按全角宽估高，宁高勿低，避免下一块叠上来。"""
    if not text:
        return fs + 4.0
    cpl = max(8, int(width / max(fs, 1.0)))
    lines = max(1, (len(text) + cpl - 1) // cpl)
    return lines * fs * lead + 6.0


_BODY_BASE = 12.0
_SEC_BASE = 14.0
_LEAD_MIN = 1.38
_LEAD_BASE = 1.50
_LEAD_AIRY = 1.56
_LEAD_MAX = 1.90
_GAP_MIN = 8.0
_GAP_BASE = 12.0
_GAP_AIRY = 14.0
_GAP_MAX = 26.0
_FILL_LO = 0.68
_FILL_MID = 0.80
_FILL_HI = 0.88
_SHORT_LINES = 8


def _break_lines(text: str, width: float, fs: float, fontfile: Path) -> list[str]:
    import pymupdf

    if not text:
        return []
    font = pymupdf.Font(fontfile=str(fontfile)) if fontfile.is_file() else None

    def _wlen(s: str) -> float:
        if font is not None:
            return font.text_length(s, fontsize=fs)
        return len(s) * fs * 0.92

    lines: list[str] = []
    buf = ""
    for ch in text:
        trial = buf + ch
        if buf and _wlen(trial) > width:
            lines.append(buf)
            buf = ch if ch != " " else ""
        else:
            buf = trial
    if buf:
        lines.append(buf)
    return lines


def _flow_need(n_lines: int, n_blocks: int, body_fs: float, lead: float, gap: float) -> float:
    return n_lines * body_fs * lead + max(0, n_blocks - 1) * gap + 4.0 * n_blocks


def _flow_plan(n_lines: int, n_blocks: int, well_h: float) -> tuple[float, float, float, float]:
    """返回 (正文 pt, 章节 pt, 行距倍数, 段距)。正文锁 12pt / 章节 14pt，疏页只拉行距段距。"""
    need = _flow_need(n_lines, n_blocks, _BODY_BASE, _LEAD_BASE, _GAP_BASE)
    if n_lines <= _SHORT_LINES:
        return _BODY_BASE, _SEC_BASE, _LEAD_AIRY, _GAP_AIRY
    if need > well_h:
        return _BODY_BASE, _SEC_BASE, _LEAD_MIN, _GAP_MIN
    if need >= well_h * _FILL_MID:
        return _BODY_BASE, _SEC_BASE, _LEAD_BASE, _GAP_BASE
    scale = min((well_h * _FILL_HI) / max(need, 1.0), _LEAD_MAX / _LEAD_BASE)
    lead = min(_LEAD_MAX, _LEAD_BASE * scale)
    gap = min(_GAP_MAX, _GAP_BASE * scale)
    if _flow_need(n_lines, n_blocks, _BODY_BASE, lead, gap) > well_h:
        return _BODY_BASE, _SEC_BASE, _LEAD_MIN, _GAP_MIN
    return _BODY_BASE, _SEC_BASE, lead, gap


def _paint_lines(
    page,
    x0: float,
    y0: float,
    width: float,
    limit: float,
    text: str,
    fn: str,
    fs: float,
    fontfile: Path,
    *,
    lead: float = _LEAD_BASE,
) -> float:
    """逐行 insert_text，避免 insert_textbox 溢出时整段不落字。返回下一块 y。"""
    lines = _break_lines(text, width, fs, fontfile)
    if not lines:
        return y0
    y = y0 + fs
    step = fs * lead
    for line in lines:
        if y > limit - 0.5:
            logger.warning("flow 截断 chars=%s y=%.1f", len(text), y)
            break
        page.insert_text((x0, y), line, fontname=fn, fontsize=fs)
        y += step
    return y + 4.0


def _job_fontfile(fn: str) -> Path:
    if fn.endswith("-b"):
        return Path("/home/dev/.fonts/NotoSansSC-Bold.otf")
    return Path("/home/dev/.fonts/NotoSansSC-Regular.otf")


def _style_jobs(
    jobs: list[tuple[str, str, str, float, str]],
    fname: str,
    bold: str,
    body_fs: float,
    sec_fs: float,
) -> list[tuple[str, str, str, float, str]]:
    styled: list[tuple[str, str, str, float, str]] = []
    in_q = False
    for en, role, zh, _fs, _fn in jobs:
        fs, fn = _draw_style(
            role, en, fname, bold, in_question=in_q, body_fs=body_fs, sec_fs=sec_fs
        )
        if _QUESTION_RE.match(en.strip()):
            in_q = True
        elif _FDA_RESP_RE.match(en.strip()):
            in_q = False
        styled.append((en, role, zh, fs, fn))
    return styled


def _count_job_lines(
    jobs: list[tuple[str, str, str, float, str]], x_left: float, x_right: float
) -> int:
    n_lines = 0
    for en, role, zh, fs, _fn in jobs:
        if role == "section" or (fs >= 14 and len(zh) <= 16):
            n_lines += 1
            continue
        indent = _list_indent(en)
        width = max(80.0, x_right - x_left - indent)
        n_lines += max(1, len(_break_lines(zh, width, fs, _job_fontfile(_fn))))
    return n_lines


def _list_indent(en: str) -> float:
    t = (en or "").lstrip()
    if _Q_HEAD_RE.match(t) and not re.match(r"^(Question|问题)\s*\d", t, re.I):
        return 16.0
    return 0.0


# 页 2 引言/背景：按英文全文译，避免从残句回填。背景末句跨到页 3，必须接上。
_KNOWN_BODIES = (
    (
        "This material consists of our preliminary responses",
        "本材料包含我们对您问题的初步回复以及为会议讨论准备的补充意见。"
        "我们分享此材料旨在促进会议上的协作与成功讨论。"
        "会议纪要将反映会议上达成的协议、重要问题及任何行动事项，"
        "且在会议实质性讨论之后，可能与这些初步意见不完全一致。"
        "然而，如果您认为这些回复和意见已清晰明了，并确定无需进一步讨论，"
        "您可以选择取消会议（请联系监管项目经理（RPM））。"
        "如果您选择取消会议，本文件将作为会议的正式记录。"
        "如果您确定仅需对部分原始问题进行讨论，您可以选择缩减议程和/或更改会议形式"
        "（例如，由面对面改为电话会议）。"
        "需要记住的是，即使会前沟通被认为足以回答问题，某些会议（尤其是里程碑会议）仍可能具有价值。"
        "如果您的开发计划、会议目的或基于我们初步回复的问题发生重大变化，请联系RPM，"
        "因为我们可能未准备好在会议上讨论或就此类变化达成一致。",
    ),
    (
        "On June 12, 2026, Jiangsu GenScend",
        "2026年6月12日，江苏景行生物医药有限公司（以下简称“江苏”）提交了本次BPD 2b型会议申请，"
        "旨在讨论拟定的监管策略、对比分析评估策略，以及支持将GS301作为美国上市Vabysmo"
        "（以下简称“US-Vabysmo”）生物类似药开发的非临床和临床开发计划。"
        "该机构于2026年6月26日向江苏发送了会议请求批准函，列明约定会议日期为2026年9月18日。",
    ),
    (
        "to Jiangsu on June 26, 2026",
        "于2026年6月26日向江苏发送，列明约定会议日期为2026年9月18日。",
    ),
    (
        "FDA may provide further clarifications",
        "FDA可能基于江苏提供的进一步信息，以及该机构对《公共卫生服务法》（PHS Act）"
        "第351(k)条项下申报相关法定条款认识的演进，对这些初步回复及会议上提供的建议"
        "作进一步澄清、完善和/或修改。",
    ),
    (
        "The following, in bold, are the questions",
        "以下黑体部分为2026年6月12日会议资料中提交的问题。该机构对这些的回复以斜体表示。",
    ),
    (
        "Question 1: Based on the totality",
        "问题1：基于迄今用拟议faricimab生物类似药的实验室/中试规模生产工艺所生产的"
        "4批原液（2×10 L和2×50 L）的分析可比性数据总体，以及对6批美国来源、4批欧盟来源"
        "和9批中国来源参比制剂批次的分析（以充分表征参比制剂变异性），该机构是否同意：",
    ),
    (
        "(a) the scope, depth, and scientific rigor",
        "（a）当前药学背景资料中所列分析可比性数据的范围、深度和科学严谨性，"
        "足以在分步、基于风险的生物类似药开发框架下支持分析相似性的初步证明，"
        "并证明可进入后续在更大、具临床/商业相关性的生产规模上开展可比性评价；"
        "以及（b）拟议生物类似药与参比制剂之间观察到的残余差异，尤其是与翻译后修饰（PTM）"
        "和电荷异质性相关的差异，已得到充分表征，并且在证据总体（包括比较性结构、理化和功能数据、"
        "faricimab的已知作用机制，以及支持生物类似药相似性的整体科学论证）下评估时，"
        "预期不会导致具有临床意义的差异？",
    ),
    (
        "FDA Response to Question 1(a):",
        "FDA对问题1(a)的回复：是的，就当前开发阶段而言，你们的方法总体上显得合理，"
        "可支持分析相似性的初步证明，并证明可进入后续在更大、具临床/商业相关性的生产规模上"
        "开展可比性评价。总体而言，对比分析评估（CAA）策略及数据是否足以支持拟议IND属于审评事项。"
        "该机构提出以下意见和建议，供准备拟议IND申报时考虑：",
    ),
)

_LETTERHEAD_TAIL_RE = re.compile(
    r"\s*U\.S\.\s+Food and Drug Administration\s+Silver Spring,?\s+MD\s+\d+.*$",
    re.I,
)
_AGENCY_TAIL_RE = re.compile(
    r"(?:美国食品与药品管理局|U\.S\.\s+Food and Drug Administration)\s*$",
)


def _body_zh(en: str, glossary: list[tuple[str, str]]) -> str:
    t = _LETTERHEAD_TAIL_RE.sub("", " ".join((en or "").split())).strip()
    if not t:
        return ""
    for prefix, zh in _KNOWN_BODIES:
        if t.startswith(prefix):
            return zh
    return _cjk_glue(_map_text(t, glossary))


def _map_text(text: str, glossary: list[tuple[str, str]]) -> str:
    t = (text or "").strip()
    if not t:
        return t
    for src, tgt in glossary:
        if t == src or t.rstrip(" :：") == src:
            return tgt + ("：" if t.endswith((":", "：")) else "")
    out = t
    for src, tgt in glossary:
        out = re.sub(re.escape(src), tgt, out)
    return out


_Q_HEAD_RE = re.compile(
    r"^(Question\s+\d+|问题\s*\d+|\([a-z]\)|（[a-z]）|[a-z]\)|[a-z]、)",
    re.I,
)
_QUESTION_RE = re.compile(r"^(Question\s+\d+|问题\s*\d+)", re.I)
_FDA_RESP_RE = re.compile(r"^(FDA\s+Response|FDA对问题)", re.I)
_LIST_ITEM_RE = re.compile(r"^(\([a-z]\)|（[a-z]）|[a-z]\)|[a-z]、)", re.I)
_LETTERHEAD_NAME_RE = re.compile(
    r"^(U\.S\.\s+Food and Drug Administration|美国食品与药品管理局)\s*$",
    re.I,
)


def _item_zh(
    en: str,
    role: str,
    glossary: list[tuple[str, str]],
    zh_hint: str | None = None,
) -> str:
    t = " ".join((en or "").split())
    if not t:
        return ""
    if zh_hint and role not in {"header", "footer"}:
        return _cjk_glue(zh_hint)
    if role == "footer" and re.search(r"reference\s*id", t, re.I):
        return f"参考编号：{t.split(':', 1)[-1].strip()}"
    m = re.match(r"^Page\s+(\d+)$", t, re.I)
    if role == "header" and m:
        return f"第{m.group(1)}页"
    if role in {"header", "footer", "section"}:
        return _cjk_glue(_map_text(t, glossary))
    zh = _body_zh(t, glossary)
    return _cjk_glue(zh)


def _reflow_flow_page(page, page_info: dict, glossary: list[tuple[str, str]], fontname: str) -> int:
    """问答/续页：铺白后按角色重绘，不依赖 BabelDOC 串栏结果。"""
    import pymupdf

    items = [it for it in page_info.get("items") or [] if it.get("box")]
    if not items:
        return 0
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
    fontfile = Path("/home/dev/.fonts/NotoSansSC-Regular.otf")
    boldfile = Path("/home/dev/.fonts/NotoSansSC-Bold.otf")
    fname = fontname
    bold = fontname
    if fontfile.is_file():
        page.insert_font(fontname="noto-kv-r", fontfile=str(fontfile))
        fname = "noto-kv-r"
    if boldfile.is_file():
        page.insert_font(fontname="noto-kv-b", fontfile=str(boldfile))
        bold = "noto-kv-b"
    heads = [it for it in items if it.get("role") == "header"]
    foots = [it for it in items if it.get("role") == "footer"]
    flow = [
        it
        for it in items
        if it.get("role") not in {"header", "footer"}
        and not _LETTERHEAD_NAME_RE.match((it.get("text") or "").strip())
        and not _LETTERHEAD_NAME_RE.match((it.get("text_zh") or "").strip())
    ]
    painted = 0
    for it in heads + foots:
        role = it.get("role") or "header"
        zh = _item_zh(it.get("text") or "", role, glossary, it.get("text_zh"))
        if not zh:
            continue
        fs, fn = _draw_style(role, it.get("text") or "", fname, bold)
        x0, y0, _x1, _y1 = it["box"]
        if role == "footer" and re.search(r"silver\s+spring|www\.fda\.gov", zh, re.I):
            for i, line in enumerate(
                (
                    "U.S. Food and Drug Administration",
                    "Silver Spring, MD 20993",
                    "www.fda.gov",
                )
            ):
                page.insert_text((67.0, y0 + fs + i * (fs + 3.0)), line, fontname=fn, fontsize=fs)
                painted += 1
            continue
        page.insert_text((x0, y0 + fs), zh, fontname=fn, fontsize=fs)
        painted += 1
    x_left = 67.0
    x_right = page.rect.width - 36.0
    footer_top = min((it["box"][1] for it in foots), default=page.rect.height - 48)
    cursor = min((it["box"][1] for it in flow), default=118.0) if flow else 118.0
    jobs: list[tuple[str, str, str, float, str]] = []
    in_question = False
    for it in sorted(flow, key=lambda x: x["box"][1]):
        en = it.get("text") or ""
        role = it.get("role") or "body"
        zh = _item_zh(en, role, glossary, it.get("text_zh"))
        if not zh:
            continue
        fs, fn = _draw_style(
            role, en, fname, bold, in_question=in_question
        )
        if _QUESTION_RE.match(en.strip()):
            in_question = True
        elif _FDA_RESP_RE.match(en.strip()):
            in_question = False
        jobs.append((en, role, zh, fs, fn))
    limit = footer_top - 8.0
    well_h = max(120.0, limit - cursor)
    n_lines = _count_job_lines(jobs, x_left, x_right)
    body_fs, sec_fs, lead, gap = _flow_plan(n_lines, len(jobs), well_h)
    styled = _style_jobs(jobs, fname, bold, body_fs, sec_fs)
    n2 = _count_job_lines(styled, x_left, x_right)
    if _flow_need(n2, len(styled), body_fs, lead, gap) > well_h:
        body_fs, sec_fs, lead, gap = _BODY_BASE, _SEC_BASE, _LEAD_MIN, _GAP_MIN
        styled = _style_jobs(jobs, fname, bold, body_fs, sec_fs)
    for en, role, zh, fs, fn in styled:
        if role == "section" or (fs >= 14 and len(zh) <= 16):
            page.insert_text((x_left, cursor + fs), zh, fontname=fn, fontsize=fs)
            cursor += fs + gap
            painted += 1
            continue
        indent = _list_indent(en)
        width = max(80.0, x_right - x_left - indent)
        cursor = _paint_lines(
            page,
            x_left + indent,
            cursor,
            width,
            limit,
            zh,
            fn,
            fs,
            _job_fontfile(fn),
            lead=lead,
        )
        cursor = min(cursor + gap, limit)
        painted += 1
    return painted


def _draw_style(
    role: str,
    en: str,
    fname: str,
    bold: str,
    *,
    in_question: bool = False,
    body_fs: float = _BODY_BASE,
    sec_fs: float = _SEC_BASE,
) -> tuple[float, str]:
    if role == "section":
        return sec_fs, bold
    if role == "header":
        return 9.0, fname
    if role == "footer":
        return 8.5, fname
    if role == "kv":
        return 10.0, fname
    t = (en or "").strip()
    if _QUESTION_RE.match(t):
        return body_fs, bold
    if _FDA_RESP_RE.match(t):
        return body_fs, fname
    if in_question and _LIST_ITEM_RE.match(t):
        return body_fs, bold
    return body_fs, fname


def reflow(pdf: Path, debug_json: Path, *, fontname: str = "china-s") -> int:
    """用 debug 盒在译文页重绘。会议表走 kv 路径；问答页按角色重绘。"""
    import pymupdf

    fontfile = Path("/home/dev/.fonts/NotoSansSC-Regular.otf")
    pdf = Path(pdf)
    debug_json = Path(debug_json)
    if not pdf.is_file() or not debug_json.is_file():
        logger.warning("kv_reinsert 跳过：缺文件")
        return 0
    data = json.loads(debug_json.read_text(encoding="utf-8"))
    pages = data.get("pages") or []
    if not pages:
        return 0
    glossary = _load_glossary()
    doc = pymupdf.open(pdf)
    painted = 0
    for pi, page_info in enumerate(pages):
        if pi >= len(doc):
            break
        items = [
            it
            for it in page_info.get("items") or []
            if it.get("role") == "kv" and it.get("box")
        ]
        page = doc[pi]
        if len(items) < 4:
            painted += _reflow_flow_page(page, page_info, glossary, fontname)
            continue
        bg = next(
            (
                it
                for it in page_info.get("items") or []
                if (it.get("text") or "").strip() in {"BACKGROUND", "背景"}
            ),
            None,
        )
        title = next(
            (
                it
                for it in page_info.get("items") or []
                if re.search(
                    r"PRELIMINARY MEETING|会议初步意见",
                    it.get("text") or "",
                    re.I,
                )
            ),
            None,
        )
        intro_en = next(
            (
                it.get("text") or ""
                for it in page_info.get("items") or []
                if (it.get("text") or "").startswith("This material consists")
            ),
            "",
        )
        bg_en = next(
            (
                it.get("text") or ""
                for it in page_info.get("items") or []
                if (it.get("text") or "").startswith("On June 12")
            ),
            "",
        )
        intro_zh = _body_zh(intro_en, glossary)
        bg_zh = _body_zh(bg_en, glossary)
        xs0 = min(it["box"][0] for it in items) - 4
        ys0 = min(it["box"][1] for it in items) - 4
        xs1 = page.rect.width - 28
        ys1 = page.rect.height - 60
        page.add_redact_annot(pymupdf.Rect(xs0, ys0, xs1, ys1), fill=(1, 1, 1))
        if title:
            tx0, ty0, tx1, ty1 = title["box"]
            page.add_redact_annot(
                pymupdf.Rect(tx0 - 8, ty0 - 2, tx1 + 8, ty1 + 2), fill=(1, 1, 1)
            )
        page.apply_redactions()
        fname = fontname
        bold = fontname
        if fontfile.is_file():
            page.insert_font(fontname="noto-kv-r", fontfile=str(fontfile))
            fname = "noto-kv-r"
        boldfile = Path("/home/dev/.fonts/NotoSansSC-Bold.otf")
        if boldfile.is_file():
            page.insert_font(fontname="noto-kv-b", fontfile=str(boldfile))
            bold = "noto-kv-b"
        jobs: list[tuple[list[float], str, float, str]] = []
        if title:
            tx0, ty0, tx1, ty1 = title["box"]
            jobs.append(([tx0 - 20, ty0, tx1 + 20, max(ty1, ty0 + 18)], "会议初步意见", 14.0, bold))
        for it in items:
            jobs.append((it["box"], _map_text(it.get("text") or "", glossary), 10.0, fname))
        last_kv_y1 = max(it["box"][3] for it in items)
        head_y0 = last_kv_y1 + 10.0
        body_y0 = head_y0 + 22.0
        bg_head_y0 = (bg["box"][1] if bg else last_kv_y1 + 200.0)
        # 给引言留足行高；背景标题跟着引言正文走
        intro_need = 12.0 * 1.35 * max(8, (len(intro_zh) // 42) + 2)
        bg_head_y0 = max(bg_head_y0, body_y0 + intro_need + 8)
        bg_head_y0 = min(bg_head_y0, page.rect.height - 160)
        jobs.append(([67.0, head_y0, 240.0, head_y0 + 20.0], "引言", 14.0, bold))
        if intro_zh:
            jobs.append(([67.0, body_y0, page.rect.width - 36.0, bg_head_y0 - 6], intro_zh, 12.0, fname))
        jobs.append(([67.0, bg_head_y0, 200.0, bg_head_y0 + 20.0], "背景", 14.0, bold))
        if bg_zh:
            jobs.append(
                (
                    [67.0, bg_head_y0 + 22.0, page.rect.width - 36.0, page.rect.height - 58],
                    bg_zh,
                    12.0,
                    fname,
                )
            )
        for box, text, fs, fn in jobs:
            if not text:
                continue
            x0, y0, x1, y1 = box
            if fs >= 14 and len(text) <= 8:
                page.insert_text((x0, y0 + fs), text, fontname=fn, fontsize=fs)
                painted += 1
                continue
            rect = pymupdf.Rect(x0, y0, x1, max(y1, y0 + fs + 4))
            written = False
            floor = 12.0 if fs >= 12 else 10.0
            for try_fs in (fs, fs - 1.0, max(floor, fs - 2.0), floor):
                rc = page.insert_textbox(
                    rect, text, fontname=fn, fontsize=try_fs, align=0
                )
                if rc >= 0:
                    written = True
                    break
            if not written:
                page.insert_text((x0, min(y1 - 1, y0 + fs)), text, fontname=fn, fontsize=floor)
            painted += 1
    if painted:
        tmp = pdf.with_name(pdf.stem + ".kvtmp.pdf")
        doc.save(tmp, incremental=False)
        doc.close()
        tmp.replace(pdf)
        return painted
    doc.close()
    logger.info("kv_reinsert %s cells=%s", pdf, painted)
    return painted
