# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：翻译记忆（精确复用 + 模糊建议 + TMX）。"""

from qyunslation.tm.match import exact_lookup, fuzzy_suggest
from qyunslation.tm.normalize import normalize_source, placeholder_signature

__all__ = [
    "exact_lookup",
    "fuzzy_suggest",
    "normalize_source",
    "placeholder_signature",
]
