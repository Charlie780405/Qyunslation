# SPDX-License-Identifier: MPL-2.0
"""PLAN-032：归档文件名清洗。

翻译流水线会在 stem 尾部追加标记（去水印、OCR、嵌图翻译、单双栏产物、语言码），
归档记录的「原文件名」必须把这些标记还原掉，否则用户在归档里看到的是产物名。

只剥已知标记且只从尾部剥，未知后缀一律保留，不猜测。
"""
from __future__ import annotations

import re
from pathlib import Path

# 尾部标记；反复剥离到稳定为止，因此顺序不敏感，可处理多层叠加
_TAIL_MARKERS: tuple[re.Pattern[str], ...] = (
    # 去水印标记可带语言码：.no_watermark / .no_watermark.zh
    re.compile(r"\.no_watermark(?:\.[^.]+)?$", re.I),
    re.compile(r"\.hpd-ocr$", re.I),
    re.compile(r"\.imgtr$", re.I),
    re.compile(r"\.letter-mono$", re.I),
    re.compile(r"\.(?:mono|dual)$", re.I),
    re.compile(r"_translated$", re.I),
    re.compile(r"\.(?:zh|zh-CN|zh-TW|zh-Hans|zh-Hant|en|ja|ko|vi)$", re.I),
)

_MAX_ROUNDS = 8


def strip_pipeline_markers(stem: str) -> str:
    """反复剥掉尾部流水线标记，直到不再变化。幂等。"""
    current = stem
    for _ in range(_MAX_ROUNDS):
        for pattern in _TAIL_MARKERS:
            stripped = pattern.sub("", current)
            if stripped != current and stripped:
                current = stripped
                break
        else:
            return current
    return current


def original_filename_from_product(product_name: str) -> str:
    """从译文产物文件名还原用户上传时的文件名。

    扩展名保持产物的扩展名：`.doc` 经规范化后产物为 `.docx` 时无法反推原扩展名，
    与其猜测不如保留，至少不带译文标记。
    """
    path = Path(product_name)
    stem = strip_pipeline_markers(path.stem)
    return f"{stem}{path.suffix}" if stem else path.name
