# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：保守的术语形态键，用于拒绝压制与词干推荐。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from qyunslation.glossary.governance import normalize_source

PREFIX_RE = re.compile(r"^(anti|non|pre)[-\s]+(.+)$", re.I)
JUNK_SUFFIX_RE = re.compile(r"[-_]?(?:pending)$", re.I)
NUMERIC_SUFFIX_RE = re.compile(r"-(?:50|75|90)$", re.I)
KEEP_STEMS = frozenset(
    {
        normalize_source("tralokinumab"),
        normalize_source("IL-13"),
        normalize_source("NHS"),
        normalize_source("EASI"),
        normalize_source("BSA"),
        normalize_source("ABC-101"),
    }
)


def strip_junk_suffix(text: str) -> str:
    """剥掉抽取伪后缀，不改词干内部连字符。"""
    source = (text or "").strip()
    source = JUNK_SUFFIX_RE.sub("", source)
    source = NUMERIC_SUFFIX_RE.sub("", source)
    return normalize_source(source)


def split_prefix(text: str) -> tuple[bool, str]:
    """返回 (是否带 anti/non/pre 前缀, 词干)。"""
    raw = strip_junk_suffix(text)
    match = PREFIX_RE.match(raw)
    if match:
        return True, normalize_source(match.group(2))
    return False, raw


def morphology_stem(text: str) -> str:
    return split_prefix(text)[1]


def canonical_surface(text: str) -> str:
    """空白/连字符折叠后的表面形式，前缀统一成 anti-X。"""
    raw = strip_junk_suffix(text)
    match = PREFIX_RE.match(raw)
    if match:
        return normalize_source(f"{match.group(1)}-{match.group(2)}")
    return raw


def has_prefix(text: str) -> bool:
    return split_prefix(text)[0]


@dataclass(frozen=True, slots=True)
class RejectedIndex:
    surfaces: frozenset[str]
    bare_stems: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.surfaces or self.bare_stems)


EMPTY_REJECTED_INDEX = RejectedIndex(frozenset(), frozenset())


def build_rejected_index(sources: list[str]) -> RejectedIndex:
    surfaces: set[str] = set()
    bare_stems: set[str] = set()
    for source in sources:
        text = (source or "").strip()
        if not text:
            continue
        surfaces.add(normalize_source(text))
        surfaces.add(canonical_surface(text))
        prefixed, stem = split_prefix(text)
        if stem and not prefixed:
            bare_stems.add(stem)
    return RejectedIndex(frozenset(surfaces), frozenset(bare_stems))


def is_rejected_source(text: str, index: RejectedIndex | None) -> bool:
    """同形或更装饰的词缀变体命中已拒集合；裸保留词不被前缀拒绝误杀。"""
    if not index or not (text or "").strip():
        return False
    exact = normalize_source(text)
    canon = canonical_surface(text)
    if exact in index.surfaces or canon in index.surfaces:
        return True
    prefixed, stem = split_prefix(text)
    if prefixed and stem and stem in index.bare_stems:
        return True
    return False
