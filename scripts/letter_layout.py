# SPDX-License-Identifier: MPL-2.0
"""书信角色标注与中文行款（PLAN-009）。不改泰州 HPD。"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

Role = str  # header|address|salutation|body|closing|signature|footer|kv|section

MERGE_ROLES = frozenset({"body", "header", "footer"})
_SECTION_TITLE_RE = re.compile(
    r"^(Introduction|引言|BACKGROUND|背景|DISCUSSION|讨论|"
    r"PRELIMINARY MEETING COMMENTS|MEETING PRELIMINARY COMMENTS|"
    r"PRELIMINARY RESPONSES TO THE QUESTIONS|对问题的初步回复|"
    r"ADDITIONAL COMMENTS?|补充意见|附加意见|"
    r"Nonclinical|Clinical Pharmacology|Clinical|Statistics|"
    r"Immunogenicity|非临床|临床药理|临床|统计|免疫原性|"
    r"PREA REQUIREMENTS|DATA STANDARDS FOR STUDIES|"
    r"SECURE EMAIL COMMUNICATIONS|LABORATORY TEST UNITS FOR CLINICAL TRIALS|"
    r"会议初步意见|CMC|药学（CMC）)\s*[:：]?\s*$",
    re.I,
)

# 会议信息表标签（长的在前，避免 Date 被 Type 截走）
# 英文必须标题式（勿把句中 indication 当标签）；中文另列
_KV_LABEL_RE = re.compile(
    r"(Meeting Date and Time|Meeting Location|Meeting Category|"
    r"Meeting Type|Application Number|Product Name|Indication|"
    r"Sponsor Name|Regulatory Pathway|"
    r"会议日期和时间|会议地点|会议类别|会议类型|申请编号|产品名称|适应症|"
    r"申办方名称|监管路径)\s*[:：]?"
)

# 行级地址提示（单行更短）
_ADDRESS_HINT_RE = re.compile(
    r"(attention|c/o|blvd|suite|nc\s*\d{5}|durham|ltd|公司|事务|大道|楼|层|收件人|转交)",
    re.I,
)


def group_for_merge(
    boxes: list[tuple[float, float, float, float, str]],
    roles: list[Role],
) -> list[tuple[list[tuple[float, float, float, float, str]], Role, bool]]:
    """按连续同角色切段，返回 (子列表, 角色, 是否允许聚合)。"""
    if not boxes:
        return []
    groups: list[tuple[list[tuple[float, float, float, float, str]], Role, bool]] = []
    cur_boxes = [boxes[0]]
    cur_role = roles[0]
    for box, role in zip(boxes[1:], roles[1:]):
        if role == cur_role:
            cur_boxes.append(box)
        else:
            groups.append((cur_boxes, cur_role, cur_role in MERGE_ROLES))
            cur_boxes = [box]
            cur_role = role
    groups.append((cur_boxes, cur_role, cur_role in MERGE_ROLES))
    return groups


_HEADER_RE = re.compile(
    r"\b(fda|pind|food\s*&\s*drug|meeting\s+preliminary)\b|美国食品药品|会议初步意见|给药",
    re.I,
)
_SALUTATION_RE = re.compile(r"^(dear\b|尊敬的)", re.I)
_CLOSING_RE = re.compile(r"^(sincerely\b|此致|敬上)", re.I)
_FOOTER_RE = re.compile(
    r"\b(enclosure|enclosures|reference\s*id|www\.fda\.gov|silver\s+spring)\b|"
    r"U\.S\.\s+Food and Drug Administration|美国食品与药品管理局|"
    r"附件|参考编号",
    re.I,
)
_LETTERHEAD_TAIL_RE = re.compile(
    r"\s*U\.S\.\s+Food and Drug Administration\s+Silver Spring,?\s+MD\s+\d+\s*$",
    re.I,
)
_SIGNATURE_NAME_RE = re.compile(
    r"\b(crystal|bland|msha|regulatory\s+health|project\s+manager)\b|"
    r"监管健康|项目经理|新药办公室|药品评价",
    re.I,
)
_TH_RE = re.compile(
    r"\(?\s*(?:\^?\s*\{\s*th\s*\}|\^\s*th)\s*\)?\s*",
    re.I,
)
_FRAGMENT_RE = re.compile(
    r"^(给药|FDA[-‑–]?|[-‑–])$",
    re.I,
)
_ADMIN_LONE_RE = re.compile(r"^administration$", re.I)
_FDA_HEAD_RE = re.compile(r"food|drug|fda|食品|药品", re.I)
_OCR_REPAIRS = (
    (re.compile(r"HealProject", re.I), "Health Project"),
    (re.compile(r"\bOphalmology\b", re.I), "Ophthalmology"),
)
_TITLE_JOIN_RE = re.compile(r"^(ophthalmology|ophalmology|眼科)$", re.I)
_CJK_PUNCT = str.maketrans(
    {
        ",": "，",
        ";": "；",
        ":": "：",
        "!": "！",
        "?": "？",
        "(": "（",
        ")": "）",
    }
)

INDENT = "　　"


def clean_text(text: str) -> str:
    """清洗 OCR 上标泄漏与碎片；中文语境下半角标点尽量全角。"""
    t = " ".join((text or "").split()).strip()
    if not t:
        return ""
    if _FRAGMENT_RE.match(t):
        return ""
    # 4 ( ^{th} ) Floor / 4th Floor → 4层（中文地址）或保留 Floor 英文
    t = re.sub(
        r"(\d+)\s*\(\s*(?:\^?\s*\{\s*th\s*\}|\^\s*th|th)\s*\)\s*(?:Floor|层)?",
        r"\1层",
        t,
        flags=re.I,
    )
    t = _TH_RE.sub("", t)
    for pat, repl in _OCR_REPAIRS:
        t = pat.sub(repl, t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = _LETTERHEAD_TAIL_RE.sub("", t).strip()
    # 若含中文则半角标点转全角（邮箱/域名除外）
    if re.search(r"[\u4e00-\u9fff]", t) and "@" not in t:
        t = t.translate(_CJK_PUNCT)
    return t


def tag_blocks(
    boxes: list[tuple[float, float, float, float, str]],
    page_w: float,
    page_h: float,
) -> list[Role]:
    """几何 + 文本判定书信角色。"""
    if not boxes:
        return []
    roles: list[Role] = ["body"] * len(boxes)
    sal_i = -1
    for i, (_x0, y0, _x1, _y1, text) in enumerate(boxes):
        if _SALUTATION_RE.search(text.strip()):
            sal_i = i
            roles[i] = "salutation"
            break

    for i, (x0, y0, x1, y1, text) in enumerate(boxes):
        t = text.strip()
        y_ratio = y0 / max(page_h, 1.0)
        x_ratio = x0 / max(page_w, 1.0)
        if roles[i] == "salutation":
            continue
        if _FOOTER_RE.search(t) or (y_ratio > 0.90 and len(t) < 40):
            roles[i] = "footer"
            continue
        if _SECTION_TITLE_RE.match(t):
            roles[i] = "section"
            continue
        if _CLOSING_RE.search(t):
            roles[i] = "closing"
            continue
        if _KV_LABEL_RE.match(t) or (
            i
            and roles[i - 1] == "kv"
            and y_ratio < 0.62
            and not t.lower().startswith("introduction")
            and not _HEADER_RE.search(t)
            and not _SECTION_TITLE_RE.match(t)
        ):
            roles[i] = "kv"
            continue
        # 页首全大写短标题是 section，不是信头
        if (
            len(t) < 64
            and re.match(r"^[A-Z][A-Z0-9 /,&'\-]{8,}$", t)
            and not re.match(r"^(PIND|PAGE)\b", t, re.I)
        ):
            roles[i] = "section"
            continue
        # 仅短信头；页首跨页续句/长段必须是 body
        if y_ratio < 0.22 and len(t) < 48 and re.match(r"^(PIND\b|Page\s+\d+|FDA\b|U\.S\.\s+FOOD)", t, re.I):
            roles[i] = "header"
            continue
        # 短信头关键词（避免正文里的 PIND 误判）
        if _HEADER_RE.search(t) and len(t) < 48 and y_ratio < 0.35:
            roles[i] = "header"
            continue
        if sal_i >= 0 and i < sal_i and x_ratio < 0.45:
            roles[i] = "address"
            continue
        if x_ratio < 0.45 and y_ratio < 0.45 and _ADDRESS_HINT_RE.search(t) and len(t) < 120:
            roles[i] = "address"
            continue
        if sal_i >= 0 and i > sal_i and x_ratio > 0.32 and (
            _SIGNATURE_NAME_RE.search(t) or x_ratio > 0.38
        ):
            # 正文下方偏右 → signature（短右栏也算）
            if y_ratio > 0.55 or _SIGNATURE_NAME_RE.search(t):
                roles[i] = "signature"
                continue
        if _SIGNATURE_NAME_RE.search(t) and x_ratio > 0.32:
            roles[i] = "signature"
            continue
        roles[i] = "body"
    return roles


def prepare_letter_boxes(
    boxes: list[tuple[float, float, float, float, str]],
    page_w: float,
    page_h: float,
) -> tuple[list[tuple[float, float, float, float, str]], list[Role]]:
    """清洗 + 丢弃空碎片，返回 (boxes, roles)。"""
    cleaned: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text in boxes:
        t = clean_text(text)
        if not t:
            continue
        cleaned.append((x0, y0, x1, y1, t))
    cleaned = split_kv_rows(cleaned, page_w)
    cleaned = split_named_sections(cleaned)
    cleaned = split_leading_caps_title(cleaned)
    cleaned = pack_kv_table(cleaned, page_w, page_h)
    cleaned = clamp_before_section_heads(cleaned)
    roles = tag_blocks(cleaned, page_w, page_h)
    return fold_short_titles(cleaned, roles)


def split_kv_rows(
    boxes: list[tuple[float, float, float, float, str]],
    page_w: float,
    *,
    tab: float | None = None,
) -> list[tuple[float, float, float, float, str]]:
    """把挤在一段里的「标签：值」拆成两列表格行，避免 BabelDOC 串栏。"""
    x_tab = float(tab if tab is not None else max(200.0, min(0.40 * page_w, 240.0)))
    out: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text in boxes:
        matches = list(_KV_LABEL_RE.finditer(text))
        if not matches or text.lower().startswith("introduction"):
            out.append((x0, y0, x1, y1, text))
            continue
        # 行不以标签开头且只有一处 → 保持原文（正文里提到 Indication 等）
        if matches[0].start() > 3 and len(matches) == 1:
            out.append((x0, y0, x1, y1, text))
            continue
        n = max(len(matches), 1)
        # 长值（适应症）多留行高，避免 insert 失败或 BabelDOC 并栏
        right = max(x1, page_w - 36.0)
        rows: list[tuple[float, float, float, float, str]] = []
        cursor = y0
        for i, m in enumerate(matches):
            chunk = text[m.start() : matches[i + 1].start() if i + 1 < n else len(text)].strip()
            lab_m = _KV_LABEL_RE.match(chunk)
            if not lab_m:
                continue
            label = lab_m.group(0).rstrip(" :：")
            value = chunk[lab_m.end() :].lstrip(" :：").strip()
            line = f"{label}: {value}".strip() if value else f"{label}:"
            h = 28.0 if len(line) > 70 else 18.0
            rows.append((x0, cursor, right, cursor + h - 0.5, line))
            cursor += h
        out.extend(rows)
    return out


_KV_ROW_H = 17.0
_KV_GAP = 8.0
_KV_LABEL_W = 178.0
_SECTION_HEAD_RE = re.compile(
    r"^(BACKGROUND|背景|DISCUSSION|讨论|ADDITIONAL COMMENTS?|补充意见|附加意见|"
    r"Introduction|引言|PRELIMINARY RESPONSES|对问题的初步回复|"
    r"Nonclinical|Clinical Pharmacology|Clinical|Statistics|"
    r"Immunogenicity|CMC|PREA REQUIREMENTS|DATA STANDARDS|"
    r"SECURE EMAIL|LABORATORY TEST UNITS)\b",
    re.I,
)


def split_named_sections(
    boxes: list[tuple[float, float, float, float, str]],
) -> list[tuple[float, float, float, float, str]]:
    """引言标题与正文拆开，避免整段叠到 BACKGROUND 上切出微字。"""
    out: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text in boxes:
        m = re.match(r"^(Introduction|引言)\s*[:：]\s*", text)
        if not m:
            out.append((x0, y0, x1, y1, text))
            continue
        rest = text[m.end() :].strip()
        head = m.group(0).strip()
        if not head.endswith((":", "：")):
            head = f"{head}:"
        out.append((x0, y0, x1, y0 + 18.0, head))
        if rest:
            out.append((x0, y0 + 22.0, x1, y1, rest))
    return out


_CAPS_LEAD_RE = re.compile(
    r"^((?:[A-Z][A-Z0-9/,&'\-]{2,}[ ]+){1,8}[A-Z][A-Z0-9/,&'\-]{2,})\s+"
    r"([A-Za-z(].+)$"
)


def split_leading_caps_title(
    boxes: list[tuple[float, float, float, float, str]],
) -> list[tuple[float, float, float, float, str]]:
    """PREA REQUIREMENTS / DATA STANDARDS 等全大写标题与正文拆开。"""
    out: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text in boxes:
        m = _CAPS_LEAD_RE.match(text.strip())
        if not m or re.match(r"^(FDA Response|Question)\b", text, re.I):
            out.append((x0, y0, x1, y1, text))
            continue
        head, rest = m.group(1).strip(), m.group(2).strip()
        if len(head) < 10 or len(rest) < 20:
            out.append((x0, y0, x1, y1, text))
            continue
        out.append((x0, y0, x1, y0 + 18.0, head))
        out.append((x0, y0 + 22.0, x1, y1, rest))
    return out


def pack_kv_table(
    boxes: list[tuple[float, float, float, float, str]],
    page_w: float,
    page_h: float,
) -> list[tuple[float, float, float, float, str]]:
    """连续 kv 行重排：左标签右值、行高一致、行距固定。"""
    is_kv: list[bool] = []
    for b in boxes:
        t = b[4]
        if re.match(r"^(Introduction|引言|BACKGROUND|背景)", t):
            is_kv.append(False)
        elif _KV_LABEL_RE.match(t):
            is_kv.append(True)
        elif is_kv and is_kv[-1] and not _SECTION_TITLE_RE.match(t) and len(t) < 200:
            is_kv.append(True)
        else:
            is_kv.append(False)
    if not any(is_kv):
        return boxes
    out: list[tuple[float, float, float, float, str]] = []
    i = 0
    while i < len(boxes):
        if not is_kv[i]:
            out.append(boxes[i])
            i += 1
            continue
        j = i
        while j < len(boxes) and is_kv[j]:
            j += 1
        y_start = boxes[i][1]
        parsed: list[list[str]] = []
        for k in range(i, j):
            t = boxes[k][4]
            m = _KV_LABEL_RE.match(t)
            if m:
                parsed.append(
                    [m.group(0).rstrip(" :："), t[m.end() :].lstrip(" :：").strip()]
                )
            elif parsed:
                parsed[-1][1] = f"{parsed[-1][1]} {t}".strip() if parsed[-1][1] else t
            else:
                parsed.append([t.rstrip(" :："), ""])
        slot = _KV_ROW_H + _KV_GAP
        x0 = min(b[0] for b in boxes[i:j])
        x_tab = x0 + _KV_LABEL_W
        x1 = max(page_w - 40.0, x_tab + 140.0)
        cursor = y_start
        for label, value in parsed:
            h = _KV_ROW_H
            y1 = cursor + h
            out.append((x0, cursor, x_tab - 4.0, y1, f"{label}:"))
            if value:
                out.append((x_tab, cursor, x1, y1, value))
            cursor = y1 + _KV_GAP
        if j < len(boxes) and cursor + 20.0 > boxes[j][1]:
            dy = cursor + 24.0 - boxes[j][1]
            boxes = list(boxes)
            for k in range(j, len(boxes)):
                if _SECTION_HEAD_RE.match(boxes[k][4].strip()) and not re.match(
                    r"^(Introduction|引言)", boxes[k][4], re.I
                ):
                    break
                bx0, by0, bx1, by1, bt = boxes[k]
                boxes[k] = (bx0, by0 + dy, bx1, by1 + dy, bt)
        i = j
    return out


def clamp_before_section_heads(
    boxes: list[tuple[float, float, float, float, str]],
    *,
    gap: float = 6.0,
) -> list[tuple[float, float, float, float, str]]:
    """引言等正文不得压住 BACKGROUND 标题，否则会被切成微字。"""
    heads = [i for i, b in enumerate(boxes) if _SECTION_HEAD_RE.match(b[4].strip())]
    if not heads:
        return boxes
    out = [list(b) for b in boxes]
    for hi in heads:
        hy0 = out[hi][1]
        hx0, hx1 = out[hi][0], out[hi][2]
        for i in range(hi):
            x0, y0, x1, y1, text = out[i]
            if y1 <= hy0 - gap:
                continue
            if min(x1, hx1) <= max(x0, hx0):
                continue
            out[i][3] = max(y0 + 14.0, hy0 - gap)
    return [(b[0], b[1], b[2], b[3], b[4]) for b in out]


def fold_short_titles(
    boxes: list[tuple[float, float, float, float, str]],
    roles: list[Role],
) -> tuple[list[tuple[float, float, float, float, str]], list[Role]]:
    """眼科并入上一行职务；丢掉信头残留的 Administration/给药。"""
    out_b: list[tuple[float, float, float, float, str]] = []
    out_r: list[Role] = []
    for box, role in zip(boxes, roles):
        t = box[4].strip()
        if role == "header" and _FRAGMENT_RE.match(t):
            continue
        if _ADMIN_LONE_RE.match(t):
            if (
                out_b
                and out_r[-1] == "header"
                and _FDA_HEAD_RE.search(out_b[-1][4])
            ):
                x0, y0, x1, y1, prev = out_b[-1]
                out_b[-1] = (x0, y0, max(x1, box[2]), max(y1, box[3]), f"{prev} Administration")
            continue
        if (
            out_b
            and role == "signature"
            and out_r[-1] == "signature"
            and _TITLE_JOIN_RE.match(t)
        ):
            x0, y0, x1, y1, prev = out_b[-1]
            out_b[-1] = (x0, y0, max(x1, box[2]), max(y1, box[3]), f"{prev} {t}")
            continue
        out_b.append(box)
        out_r.append(role)
    return out_b, out_r


def role_font_size(role: Role, profile: dict[str, Any]) -> float:
    meta = float(profile.get("meta_font_size") or 9.0)
    mapping = {
        "header": meta,
        "address": meta,
        "salutation": float(profile.get("salutation_font_size") or 10.5),
        "body": float(profile.get("body_font_size") or 12.0),
        "closing": float(profile.get("closing_font_size") or 9.5),
        "signature": meta,
        "footer": float(profile.get("footer_font_size") or 8.5),
        "kv": float(profile.get("kv_font_size") or 10.0),
        "section": float(profile.get("section_font_size") or 14.0),
    }
    return mapping.get(role, meta)


def role_line_skip(role: Role, profile: dict[str, Any]) -> float:
    if role in {"address", "signature", "header", "footer", "closing", "kv"}:
        return float(profile.get("signature_line_skip") or 1.25)
    return float(profile.get("line_skip") or 1.5)


def tag_paragraph_text(text: str, *, y_ratio: float, x_ratio: float) -> Role:
    """译后段落角色（中文）。"""
    t = (text or "").strip()
    # 去掉可能已存在的缩进/坏映射前缀
    t = t.lstrip(INDENT).lstrip("\u0474").lstrip()
    if _FOOTER_RE.search(t) or (y_ratio > 0.90 and len(t) < 40):
        return "footer"
    if _SECTION_TITLE_RE.match(t):
        return "section"
    if _CLOSING_RE.search(t):
        return "closing"
    if _SALUTATION_RE.search(t):
        return "salutation"
    if _KV_LABEL_RE.match(t) or t in {
        "GS301",
        "182646",
        "线上",
        "生物类似药",
        "BPD 2b型",
        "BPD Type 2b",
    } or (
        0.18 < y_ratio < 0.55
        and x_ratio > 0.28
        and len(t) < 180
        and not re.match(r"^(引言|本材料|我们分享|BACKGROUND|背景|会议初步)", t)
        and re.search(
            r"生物类似药|BPD|虚拟|线上|申请编号|适应症|351|Vabysmo|GS301|"
            r"景行|江苏|公共卫生|东部标准|182646|faricimab|Biosimilar",
            t,
            re.I,
        )
    ):
        return "kv"
    if y_ratio < 0.22 and len(t) < 48:
        return "header"
    if _HEADER_RE.search(t) and len(t) < 48 and y_ratio < 0.35:
        return "header"
    if x_ratio > 0.32 and y_ratio > 0.55 and (
        _SIGNATURE_NAME_RE.search(t) or len(t) < 80
    ):
        return "signature"
    # 地址：称谓之上左栏，可较长
    if x_ratio < 0.45 and y_ratio < 0.40:
        if re.search(
            r"(ltd|公司|事务|大道|楼|层|durham|blvd|attention|c/o|suite|"
            r"nc\s*\d{5}|收件人|转交)",
            t,
            re.I,
        ):
            return "address"
    return "body"


def ensure_body_indent(text: str) -> str:
    t = text or ""
    if not t.strip():
        return t
    if t.startswith(INDENT) or t.startswith("\u0474\u0474"):
        return t
    # 称谓/落款/附件不缩；过短碎片不缩（避免 OCR 碎字被加缩进）
    stripped = t.strip()
    if _SALUTATION_RE.search(stripped) or _CLOSING_RE.search(stripped) or _FOOTER_RE.search(
        stripped
    ):
        return t
    if len(stripped) < 12:
        return t
    return INDENT + t.lstrip()
