# SPDX-License-Identifier: MPL-2.0
"""PLAN-027a：文档内嵌图判定策略（stdlib + PIL only，可跨 venv 按路径加载）。"""
from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

# 物理显示门槛（pt）
MIN_LONG_EDGE_PT = float(os.environ.get("QYUNSLATION_DOC_IMAGE_MIN_LONG_PT", "150"))
MIN_AREA_PT2 = float(os.environ.get("QYUNSLATION_DOC_IMAGE_MIN_AREA_PT", "25000"))
MAX_PAGE_FRAC = float(os.environ.get("QYUNSLATION_DOC_IMAGE_MAX_PAGE_FRAC", "0.90"))
BANNER_ASPECT = float(os.environ.get("QYUNSLATION_DOC_IMAGE_BANNER_ASPECT", "8"))
BANNER_SHORT_PT = float(os.environ.get("QYUNSLATION_DOC_IMAGE_BANNER_SHORT_PT", "20"))
# 像素几何兜底（无显示尺寸时）
MIN_EDGE_PX = int(os.environ.get("QYUNSLATION_DOC_IMAGE_MIN_PX", "200"))
MIN_AREA_PX = int(os.environ.get("QYUNSLATION_DOC_IMAGE_MIN_AREA_PX", "40000"))

_NUM_ONLY_RE = re.compile(
    r"^[\d\s\.\,\+\-\*\/\=\%\:\;\(\)\[\]\{\}℃°\<\>\±×÷~～]+$"
)
_UNIT_RE = re.compile(
    r"^(?:mg|mL|ml|kg|g|µg|ug|ng|μg|mm|cm|m|w|h|d|wk|weeks?|days?|hrs?|"
    r"IU|U|%|ppm|nM|µM|uM|mM|M|pg|ng/mL|mg/kg)$",
    re.I,
)
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HAS_LATIN_RE = re.compile(r"[A-Za-z]{2,}")


@dataclass
class ImageDecision:
    should_translate: bool
    reason: str
    translatable_blocks: int = 0
    source_lang: str = "unknown"
    feature_hash: str = ""
    detected_blocks: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def feature_hash(img_bytes: bytes) -> str:
    return hashlib.sha256(img_bytes).hexdigest()[:16]


def _target_is_chinese(target_lang: str) -> bool:
    t = (target_lang or "").lower()
    return any(x in t for x in ("中文", "chinese", "zh", "简体", "繁体"))


def _target_is_english(target_lang: str) -> bool:
    t = (target_lang or "").lower()
    return any(x in t for x in ("english", "en", "英文"))


def is_numeric_or_unit(text: str) -> bool:
    """纯数字/标点/单位，不送翻译。"""
    s = (text or "").strip()
    if not s:
        return True
    if _NUM_ONLY_RE.match(s):
        return True
    if _UNIT_RE.match(s):
        return True
    # 数字+单位：16w / 100mg / Week 16（弱形式仍可能有语义，留给语种门控）
    if re.match(r"^[\d\.\,\s]+(?:mg|mL|ml|kg|g|µg|ug|ng|mm|cm|%|w|h|d)$", s, re.I):
        return True
    return False


def detect_lang_of_texts(texts: Sequence[str]) -> str:
    """粗判图内文字语种：zh / en / mixed / num_only / unknown。"""
    usable = [t.strip() for t in texts if t and t.strip()]
    if not usable:
        return "unknown"
    non_num = [t for t in usable if not is_numeric_or_unit(t)]
    if not non_num:
        return "num_only"
    has_cjk = any(_HAS_CJK_RE.search(t) for t in non_num)
    has_lat = any(_HAS_LATIN_RE.search(t) for t in non_num)
    if has_cjk and has_lat:
        return "mixed"
    if has_cjk:
        return "zh"
    if has_lat:
        return "en"
    return "unknown"


def filter_translatable_texts(
    texts: Sequence[str], *, target_lang: str = "简体中文"
) -> tuple[list[str], str, str]:
    """过滤不可译块；返回 (可译文本列表, detected_lang, skip_reason_or_空)。"""
    detected = detect_lang_of_texts(texts)
    kept = [t for t in texts if t and t.strip() and not is_numeric_or_unit(t)]
    if not kept:
        return [], detected, "no_translatable_text"
    if detected == "num_only":
        return [], detected, "no_translatable_text"

    if _target_is_english(target_lang) and detected == "en":
        # 中译英且图内已是英文
        return [], detected, "already_target_lang"
    if _target_is_chinese(target_lang) and detected == "zh":
        # 英译中且图内已是中文（无拉丁词）
        return [], detected, "already_target_lang"

    return kept, detected, ""


def _pixel_size(img_bytes: bytes) -> tuple[int, int]:
    if not img_bytes or Image is None:
        return 0, 0
    try:
        with Image.open(io.BytesIO(img_bytes)) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return 0, 0


def evaluate_geometry(
    *,
    display_width_pt: float | None = None,
    display_height_pt: float | None = None,
    page_frac: float | None = None,
    is_header: bool = False,
    pixel_w: int = 0,
    pixel_h: int = 0,
) -> tuple[bool, str]:
    """几何初筛；不依赖 OCR。返回 (ok, reason)。"""
    if page_frac is not None and page_frac > MAX_PAGE_FRAC:
        return False, "full_page_scan"

    dw = float(display_width_pt or 0)
    dh = float(display_height_pt or 0)
    if dw > 0 and dh > 0:
        long_edge = max(dw, dh)
        short_edge = min(dw, dh)
        area = dw * dh
        if long_edge < MIN_LONG_EDGE_PT or area < MIN_AREA_PT2:
            return False, "too_small"
        if short_edge < BANNER_SHORT_PT and (long_edge / max(short_edge, 1e-6)) > BANNER_ASPECT:
            return False, "banner_line"
        if is_header and long_edge < 120:
            return False, "too_small_header_logo"
        return True, "ok"

    # 无显示尺寸时退回像素门槛
    if pixel_w > 0 and pixel_h > 0:
        if min(pixel_w, pixel_h) < MIN_EDGE_PX or pixel_w * pixel_h < MIN_AREA_PX:
            return False, "too_small"
        if is_header and min(pixel_w, pixel_h) < 80:
            return False, "too_small_header_logo"
        return True, "ok"

    return False, "too_small"


def evaluate_image_candidate(
    img_bytes: bytes,
    display_width_pt: float = 0.0,
    display_height_pt: float = 0.0,
    target_lang: str = "简体中文",
    page_frac: float | None = None,
    is_header: bool = False,
    ocr_texts: Iterable[str] | None = None,
) -> ImageDecision:
    """根据物理显示尺寸 + 可选 OCR 文本做判定。"""
    fh = feature_hash(img_bytes or b"")
    pw, ph = _pixel_size(img_bytes or b"")
    ok, reason = evaluate_geometry(
        display_width_pt=display_width_pt,
        display_height_pt=display_height_pt,
        page_frac=page_frac,
        is_header=is_header,
        pixel_w=pw,
        pixel_h=ph,
    )
    if not ok:
        return ImageDecision(
            should_translate=False,
            reason=reason,
            feature_hash=fh,
        )

    if ocr_texts is None:
        # 仅几何通过，等 probe/OCR 再精确化
        return ImageDecision(
            should_translate=True,
            reason="ok",
            feature_hash=fh,
            source_lang="unknown",
        )

    texts = list(ocr_texts)
    kept, lang, skip = filter_translatable_texts(texts, target_lang=target_lang)
    if skip:
        return ImageDecision(
            should_translate=False,
            reason=skip,
            translatable_blocks=0,
            source_lang=lang,
            feature_hash=fh,
            detected_blocks=len(texts),
        )
    return ImageDecision(
        should_translate=True,
        reason="ok",
        translatable_blocks=len(kept),
        source_lang=lang,
        feature_hash=fh,
        detected_blocks=len(texts),
    )
