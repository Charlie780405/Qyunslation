# SPDX-License-Identifier: MPL-2.0
"""文档类型模板：load / detect / apply / 运行时行距 patch。不改泰州 HPD。"""
from __future__ import annotations

import logging
import re
import sys
import types
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROFILES_PATH = Path(__file__).resolve().parent / "doc_profiles.toml"
AUTO_CHOICE = "自动"
PROFILE_ORDER = ("letter", "literature", "regulatory", "generic")

_LETTER_RE = re.compile(
    r"\b(dear|sincerely|enclosure|enclosures|pind)\b|此致|尊敬的|会议初步意见",
    re.I,
)
_LIT_RE = re.compile(
    r"\b(abstract|doi|references|introduction|methods|conclusion)\b|参考文献|摘要",
    re.I,
)
_REG_RE = re.compile(
    r"\b(21\s*cfr|ind\b|module\s*[1-5]|ctd|ich\s*m4)\b|申报资料|共线|药学",
    re.I,
)


def load(path: Path | None = None) -> dict[str, dict[str, Any]]:
    import tomllib

    src = path or PROFILES_PATH
    data = tomllib.loads(src.read_text(encoding="utf-8"))
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def labels(profiles: dict[str, dict[str, Any]] | None = None) -> list[str]:
    data = profiles or load()
    return [str(data[k]["label"]) for k in PROFILE_ORDER if k in data]


def name_from_choice(choice: str | None, profiles: dict[str, dict[str, Any]] | None = None) -> str:
    if not choice or choice == AUTO_CHOICE or str(choice).startswith(AUTO_CHOICE):
        return "auto"
    data = profiles or load()
    for name, prof in data.items():
        if choice == name or choice == prof.get("label"):
            return name
    return "auto"


def hint_choice(detected: str, profiles: dict[str, dict[str, Any]] | None = None) -> str:
    data = profiles or load()
    label = data.get(detected, {}).get("label", detected)
    return f"{AUTO_CHOICE}（识别为：{label}）"


def detect(pdf_path: Path, *, max_chars: int = 4000) -> str:
    """启发式：letter / literature / regulatory / generic。不调用泰州 HPD。"""
    text = ""
    try:
        import pymupdf

        doc = pymupdf.open(pdf_path)
        try:
            text = "".join((p.get_text() or "") for p in doc[:3])
        finally:
            doc.close()
    except Exception as exc:
        logger.warning("detect 读 PDF 失败: %s", exc)
    blob = f"{Path(pdf_path).name}\n{text[:max_chars]}"
    letter = bool(_LETTER_RE.search(blob))
    lit = bool(_LIT_RE.search(blob))
    reg = bool(_REG_RE.search(blob))
    if letter:
        return "letter"
    if lit:
        return "literature"
    if reg:
        return "regulatory"
    return "generic"


def resolve(choice: str | None, pdf_path: Path | None) -> str:
    name = name_from_choice(choice)
    if name != "auto":
        return name
    if pdf_path:
        return detect(Path(pdf_path))
    return "generic"


def get(name: str, profiles: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    data = profiles or load()
    key = name if name in data else "generic"
    prof = dict(data[key])
    prof["name"] = key
    return prof


def apply(name: str, settings: Any) -> dict[str, Any]:
    prof = get(name)
    pdf = getattr(settings, "pdf", None)
    trans = getattr(settings, "translation", None)
    if trans is not None and hasattr(trans, "primary_font_family"):
        trans.primary_font_family = prof.get("primary_font_family")
    if pdf is not None:
        if hasattr(pdf, "split_short_lines"):
            pdf.split_short_lines = bool(prof.get("split_short_lines", False))
        if hasattr(pdf, "short_line_split_factor"):
            pdf.short_line_split_factor = float(prof.get("short_line_split_factor", 0.8))
        if hasattr(pdf, "disable_rich_text_translate"):
            pdf.disable_rich_text_translate = bool(
                prof.get("disable_rich_text_translate", False)
            )
        if hasattr(pdf, "no_merge_alternating_line_numbers"):
            pdf.no_merge_alternating_line_numbers = not bool(
                prof.get("merge_alternating_line_numbers", True)
            )
    logger.info("应用文档模板 %s %s", prof.get("name"), prof.get("label"))
    return prof


def patch_letter_typesetting(profile: dict[str, Any] | None = None) -> bool:
    """译后按书信角色改字号/段首缩进/落款右齐。仅 letter 模板启用。"""
    prof = profile or get("letter")
    if prof.get("name") != "letter" and "body_font_size" not in prof:
        return False
    try:
        from babeldoc.format.pdf.document_il.midend import typesetting
        from babeldoc.format.pdf.document_il import il_version_1
    except Exception as exc:
        logger.warning("patch_letter_typesetting 无法 import: %s", exc)
        return False

    try:
        from letter_layout import (
            ensure_body_indent,
            role_font_size,
            role_line_skip,
            tag_paragraph_text,
            INDENT,
        )
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from letter_layout import (  # type: ignore
            ensure_body_indent,
            role_font_size,
            role_line_skip,
            tag_paragraph_text,
            INDENT,
        )

    cls = getattr(typesetting, "Typesetting", None)
    if cls is None or not hasattr(cls, "render_paragraph"):
        logger.warning("patch_letter_typesetting: render_paragraph 不存在")
        return False

    typesetting._QY_LETTER_PROFILE = dict(prof)
    if getattr(cls.render_paragraph, "_qy_letter_patched", False):
        return True

    raw_rp = cls.render_paragraph
    raw_fn = raw_rp.__func__ if isinstance(raw_rp, types.MethodType) else raw_rp

    def _para_unicode(paragraph) -> str:
        parts: list[str] = []
        for comp in paragraph.pdf_paragraph_composition or []:
            if comp.pdf_line:
                for ch in comp.pdf_line.pdf_character or []:
                    if ch.char_unicode:
                        parts.append(ch.char_unicode)
            elif getattr(comp, "pdf_character", None):
                if comp.pdf_character.char_unicode:
                    parts.append(comp.pdf_character.char_unicode)
            elif getattr(comp, "pdf_same_style_characters", None):
                for ch in comp.pdf_same_style_characters.pdf_character or []:
                    if ch.char_unicode:
                        parts.append(ch.char_unicode)
            elif getattr(comp, "pdf_same_style_unicode_characters", None):
                u = comp.pdf_same_style_unicode_characters.unicode
                if u:
                    parts.append(u)
        return "".join(parts)

    def _set_para_fontsize(paragraph, fs: float) -> None:
        if paragraph.pdf_style is None:
            paragraph.pdf_style = il_version_1.PdfStyle(
                font_id="base", font_size=fs, graphic_state=il_version_1.GraphicState()
            )
        else:
            paragraph.pdf_style.font_size = fs
        for comp in paragraph.pdf_paragraph_composition or []:
            if comp.pdf_line:
                for ch in comp.pdf_line.pdf_character or []:
                    if ch.pdf_style:
                        ch.pdf_style.font_size = fs
            if getattr(comp, "pdf_character", None) and comp.pdf_character.pdf_style:
                comp.pdf_character.pdf_style.font_size = fs
            if getattr(comp, "pdf_same_style_characters", None):
                sc = comp.pdf_same_style_characters
                if sc.pdf_style:
                    sc.pdf_style.font_size = fs
                for ch in sc.pdf_character or []:
                    if ch.pdf_style:
                        ch.pdf_style.font_size = fs
            if getattr(comp, "pdf_same_style_unicode_characters", None):
                su = comp.pdf_same_style_unicode_characters
                if su.pdf_style:
                    su.pdf_style.font_size = fs

    def _prepend_indent(paragraph) -> None:
        text = _para_unicode(paragraph)
        if text.startswith(INDENT):
            return
        new_text = ensure_body_indent(text)
        if new_text == text or not new_text.startswith(INDENT):
            return
        try:
            style = paragraph.pdf_style
            indent_comp = il_version_1.PdfParagraphComposition(
                pdf_same_style_unicode_characters=il_version_1.PdfSameStyleUnicodeCharacters(
                    unicode=INDENT,
                    pdf_style=style,
                )
            )
            paragraph.pdf_paragraph_composition = [
                indent_comp,
                *(paragraph.pdf_paragraph_composition or []),
            ]
            if paragraph.unicode:
                paragraph.unicode = INDENT + paragraph.unicode.lstrip()
            # 已插入字符时关闭 first_line_indent，避免双重缩进
            paragraph.first_line_indent = False
        except Exception as exc:
            logger.warning("body 缩进注入失败，回退 first_line_indent: %s", exc)
            try:
                paragraph.first_line_indent = True
            except Exception:
                pass

    def _shift_unit(u, shift: float) -> None:
        if getattr(u, "char", None) and u.char and u.char.box:
            u.char.box.x += shift
            u.char.box.x2 += shift
            if u.char.visual_bbox and u.char.visual_bbox.box:
                u.char.visual_bbox.box.x += shift
                u.char.visual_bbox.box.x2 += shift
            u.box_cache = None
        elif getattr(u, "unicode", None) is not None and u.x is not None:
            u.x += shift
            u.box_cache = None
        elif getattr(u, "formular", None) and u.formular and u.formular.box:
            u.formular.box.x += shift
            u.formular.box.x2 += shift
            for ch in u.formular.pdf_character or []:
                if ch.box:
                    ch.box.x += shift
                    ch.box.x2 += shift
            u.box_cache = None

    orig_layout = cls._layout_typesetting_units

    def _layout_with_align(
        self,
        typesetting_units,
        box,
        scale,
        line_skip=1.5,
        paragraph=None,
        use_english_line_break=True,
        *args,
        **kwargs,
    ):
        override = getattr(self, "_qy_para_line_skip", None)
        if override is not None:
            line_skip = float(override)
        units, ok = orig_layout(
            self,
            typesetting_units,
            box,
            scale,
            line_skip,
            paragraph,
            use_english_line_break,
            *args,
            **kwargs,
        )
        align = getattr(self, "_qy_para_align", "left")
        if align == "right" and units and box is not None:
            try:
                max_x2 = max(u.box.x2 for u in units if u.box)
                shift = float(box.x2) - float(max_x2)
                if abs(shift) > 0.5:
                    for u in units:
                        _shift_unit(u, shift)
            except Exception as exc:
                logger.warning("signature 右齐失败，保持左齐: %s", exc)
        return units, ok

    def _render_paragraph(self, paragraph, page, fonts):
        prof_local = getattr(typesetting, "_QY_LETTER_PROFILE", None) or prof
        box = paragraph.box
        page_h = 842.0
        page_w = 595.0
        try:
            if page.cropbox and page.cropbox.box:
                page_h = max(page.cropbox.box.y2 - page.cropbox.box.y, 1.0)
                page_w = max(page.cropbox.box.x2 - page.cropbox.box.x, 1.0)
            elif page.mediabox and page.mediabox.box:
                page_h = max(page.mediabox.box.y2 - page.mediabox.box.y, 1.0)
                page_w = max(page.mediabox.box.x2 - page.mediabox.box.x, 1.0)
        except Exception:
            pass
        text = _para_unicode(paragraph)
        area = (box.x2 - box.x) * (box.y2 - box.y) if box else 0.0
        # BabelDOC Box：y=底、y2=顶（PDF 坐标）；换算为自上而下比例
        if box and box.y2 is not None:
            y_ratio = (page_h - float(box.y2)) / page_h
        elif box and box.y is not None:
            y_ratio = (page_h - float(box.y)) / page_h
        else:
            y_ratio = 0.5
        x_ratio = (float(box.x) / page_w) if box and box.x is not None else 0.0
        role = tag_paragraph_text(text, y_ratio=y_ratio, x_ratio=x_ratio)
        if role == "header" and text.strip() in {"管理", "给药", "管理局", "Administration"}:
            logger.warning("跳过信头 Administration 残片 text=%r", text[:20])
            return
        # 只丢正文微碎片；信头/落款/机构专名即使短也要留下
        if (
            role == "body"
            and area < 400.0
            and len(text.strip()) < 8
        ):
            logger.warning("跳过微段落碎片 area=%.0f text=%r", area, text[:20])
            return
        fs = role_font_size(role, prof_local)
        _set_para_fontsize(paragraph, fs)
        if role == "body" and bool(prof_local.get("body_first_indent", True)):
            # BabelDOC first_line_indent ≈ 两汉字宽；不用 U+3000（思源映射易变成 Ѵ）
            try:
                paragraph.first_line_indent = True
            except Exception as exc:
                logger.warning("first_line_indent 失败，尝试字符缩进: %s", exc)
                _prepend_indent(paragraph)
        self._qy_para_align = (
            "right"
            if role in {"signature", "closing"}
            and str(prof_local.get("signature_align") or "right") == "right"
            else "left"
        )
        self._qy_para_line_skip = role_line_skip(role, prof_local)
        # 从 1.0 起再找最优缩放，避免预处理字号下的过小 scale
        try:
            paragraph.optimal_scale = 1.0
        except Exception:
            pass
        try:
            return raw_fn(self, paragraph, page, fonts)
        finally:
            self._qy_para_align = "left"
            self._qy_para_line_skip = None

    if not getattr(orig_layout, "_qy_letter_align_patched", False):
        _layout_with_align._qy_letter_align_patched = True  # type: ignore[attr-defined]
        cls._layout_typesetting_units = _layout_with_align

    _render_paragraph._qy_letter_patched = True  # type: ignore[attr-defined]
    cls.render_paragraph = _render_paragraph
    logger.info("已注入 letter 角色排版 patch")
    return True


def patch_line_skip(value: float) -> bool:
    """运行时改 Typesetting 内硬编码 1.50/1.3；函数不存在则降级。"""
    try:
        from babeldoc.format.pdf.document_il.midend import typesetting
    except Exception as exc:
        logger.warning("patch_line_skip 无法 import typesetting: %s", exc)
        return False
    cls = getattr(typesetting, "Typesetting", None)
    fn = getattr(cls, "_find_optimal_scale_and_layout", None) if cls else None
    if fn is None:
        logger.warning("patch_line_skip: Typesetting._find_optimal_scale_and_layout 不存在")
        return False
    typesetting._QY_LINE_SKIP = float(value)
    if getattr(fn, "_qy_line_skip_wrapped", False):
        return True

    raw = fn.__func__ if isinstance(fn, types.MethodType) else fn

    def _wrapped(self, *args, **kwargs):
        skip = getattr(typesetting, "_QY_LINE_SKIP", None)
        if skip is None:
            return raw(self, *args, **kwargs)
        skip_f = float(skip)
        if abs(skip_f - 1.5) < 0.02 or abs(skip_f - 1.3) < 0.02:
            old = self.is_cjk
            self.is_cjk = abs(skip_f - 1.5) < 0.02
            try:
                return raw(self, *args, **kwargs)
            finally:
                self.is_cjk = old
        code = raw.__code__
        consts = [
            skip_f if c in (1.5, 1.50, 1.3) else c for c in code.co_consts
        ]
        if tuple(consts) == code.co_consts:
            logger.warning("patch_line_skip: 未找到 1.50/1.3 常量")
            return raw(self, *args, **kwargs)
        new_fn = types.FunctionType(
            code.replace(co_consts=tuple(consts)),
            raw.__globals__,
            raw.__name__,
            raw.__defaults__,
            raw.__closure__,
        )
        return new_fn(self, *args, **kwargs)

    _wrapped._qy_line_skip_wrapped = True  # type: ignore[attr-defined]
    cls._find_optimal_scale_and_layout = _wrapped
    logger.info("已注入 line_skip=%s", value)
    return True
