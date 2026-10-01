# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：译前术语解析的确定性快路径和语义降级接口。

The resolver deliberately keeps the exact/alias path independent from the
embedding service.  A confirmed term should be resolved from the local index
on every subsequent translation; semantic search is only a fallback for text
that has no approved exact match.

PLAN-073b：全大写缩写与 ≤3 字符源词区分大小写匹配，避免 PP/No 误命中正文。
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache


LAYER_PRIORITY = {
    "org": 100,
    "form": 95,
    "project": 90,
    "clinical": 80,
    "session": 40,
    "harvest": 20,
}

_CASE_SENSITIVE_RE = re.compile(r"^[A-Z]{2,}(?:-[A-Z0-9]+)*$")


def normalize_term(value: str) -> str:
    """Normalize a term without changing its human-readable representation."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.strip().split()).casefold()


def normalize_term_preserve_case(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.strip().split())


def term_requires_case_sensitive(source: str) -> bool:
    """PLAN-073b：短词与全大写缩写必须区分大小写。"""
    stripped = (source or "").strip()
    if not stripped:
        return False
    if len(stripped) <= 3:
        return True
    return bool(_CASE_SENSITIVE_RE.fullmatch(stripped))


@dataclass(frozen=True, slots=True)
class TermRecord:
    concept_id: str
    source_term: str
    target_term: str
    layer: str = "clinical"
    src_lang: str = "en"
    tgt_lang: str = "zh"
    role: str = "preferred"
    term_type: str = "general"
    do_not_translate: bool = False
    forbidden_targets: tuple[str, ...] = ()

    @property
    def normalized_source(self) -> str:
        return normalize_term(self.source_term)

    @property
    def case_sensitive(self) -> bool:
        return term_requires_case_sensitive(self.source_term)

    @property
    def priority(self) -> int:
        return LAYER_PRIORITY.get(self.layer.casefold(), 0)


@dataclass(frozen=True, slots=True)
class TermMatch:
    concept_id: str
    source_term: str
    target_term: str
    start: int
    end: int
    match_type: str
    layer: str
    role: str
    term_type: str
    confidence: float
    do_not_translate: bool
    forbidden_targets: tuple[str, ...]
    matched_text: str = ""


class _TrieNode:
    __slots__ = ("children", "records")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.records: list[TermRecord] = []


@dataclass(frozen=True, slots=True)
class TermIndex:
    case_insensitive: _TrieNode
    case_sensitive: _TrieNode


def _record_key(record: TermRecord) -> tuple[int, int, str, str]:
    return (
        record.priority,
        1 if record.role == "preferred" else 0,
        len(record.normalized_source),
        record.concept_id,
    )


def _insert_record(root: _TrieNode, record: TermRecord, *, preserve_case: bool) -> None:
    key = (
        normalize_term_preserve_case(record.source_term)
        if preserve_case
        else record.normalized_source
    )
    if not key or not record.target_term.strip():
        return
    node = root
    for char in key:
        node = node.children.setdefault(char, _TrieNode())
    node.records.append(record)


def build_term_index(records: Iterable[TermRecord]) -> TermIndex:
    """Build case-insensitive and case-sensitive tries."""
    ci_root = _TrieNode()
    cs_root = _TrieNode()
    by_key: dict[tuple[str, str, str, str, bool], TermRecord] = {}
    for record in records:
        preserve = record.case_sensitive
        source_key = (
            normalize_term_preserve_case(record.source_term)
            if preserve
            else record.normalized_source
        )
        if not source_key:
            continue
        dedupe_key = (
            source_key,
            record.src_lang.casefold(),
            record.tgt_lang.casefold(),
            record.concept_id,
            preserve,
        )
        previous = by_key.get(dedupe_key)
        if previous is None or _record_key(record) > _record_key(previous):
            by_key[dedupe_key] = record
    for record in by_key.values():
        _insert_record(
            cs_root if record.case_sensitive else ci_root,
            record,
            preserve_case=record.case_sensitive,
        )
    for root in (ci_root, cs_root):
        for node in _walk_nodes(root):
            node.records.sort(key=_record_key, reverse=True)
    return TermIndex(case_insensitive=ci_root, case_sensitive=cs_root)


def _walk_nodes(root: _TrieNode) -> Iterable[_TrieNode]:
    yield root
    for child in root.children.values():
        yield from _walk_nodes(child)


def _is_ascii_word_char(char: str) -> bool:
    return bool(char) and (char.isascii() and (char.isalnum() or char == "_"))


def _valid_boundary(text: str, start: int, end: int) -> bool:
    """Avoid matching ``event`` inside ``events`` while allowing CJK text."""
    if start > 0 and _is_ascii_word_char(text[start - 1]) and _is_ascii_word_char(text[start]):
        return False
    if end < len(text) and _is_ascii_word_char(text[end - 1]) and _is_ascii_word_char(text[end]):
        return False
    return True


def _choose_record(records: list[TermRecord]) -> TermRecord:
    return max(records, key=_record_key)


def _match_to_result(
    record: TermRecord, start: int, end: int, match_type: str, *, matched_text: str
) -> TermMatch:
    return TermMatch(
        concept_id=record.concept_id,
        source_term=record.source_term,
        target_term=record.target_term,
        start=start,
        end=end,
        match_type=match_type,
        layer=record.layer,
        role=record.role,
        term_type=record.term_type,
        confidence=1.0 if match_type in {"exact", "alias"} else 0.0,
        do_not_translate=record.do_not_translate,
        forbidden_targets=record.forbidden_targets,
        matched_text=matched_text,
    )


def _exact_matches(root: _TrieNode, text: str, *, preserve_case: bool) -> list[TermMatch]:
    normalized = normalize_term_preserve_case(text) if preserve_case else normalize_term(text)
    if not normalized:
        return []
    out: list[TermMatch] = []
    cursor = 0
    while cursor < len(normalized):
        node = root
        index = cursor
        best: tuple[int, TermRecord] | None = None
        while index < len(normalized) and normalized[index] in node.children:
            node = node.children[normalized[index]]
            index += 1
            if node.records and _valid_boundary(normalized, cursor, index):
                best = (index, _choose_record(node.records))
        if best is None:
            cursor += 1
            continue
        end, record = best
        match_type = "alias" if record.role in {"synonym", "abbreviation"} else "exact"
        out.append(
            _match_to_result(
                record,
                cursor,
                end,
                match_type,
                matched_text=normalized[cursor:end],
            )
        )
        cursor = end
    return out


def _merge_matches(*groups: Iterable[TermMatch]) -> list[TermMatch]:
    seen: set[tuple[str, int, int]] = set()
    merged: list[TermMatch] = []
    for group in groups:
        for match in group:
            key = (match.concept_id, match.start, match.end)
            if key in seen:
                continue
            seen.add(key)
            merged.append(match)
    return sorted(merged, key=lambda item: (item.start, -len(item.source_term)))


class TermResolver:
    """Resolve approved terms before translation, with a semantic fallback."""

    def __init__(
        self,
        index: TermIndex | _TrieNode,
        *,
        semantic_resolver: Callable[[str], Iterable[TermRecord | TermMatch]] | None = None,
        cache_size: int = 512,
    ) -> None:
        if isinstance(index, TermIndex):
            self.index = index
        else:
            # Backward compatibility: single trie treated as case-insensitive only.
            self.index = TermIndex(case_insensitive=index, case_sensitive=_TrieNode())
        self.semantic_resolver = semantic_resolver
        self._resolve_cached = lru_cache(maxsize=max(1, cache_size))(self._resolve_uncached)

    def resolve(self, text: str) -> list[TermMatch]:
        return list(self._resolve_cached(text or ""))

    def _resolve_uncached(self, text: str) -> tuple[TermMatch, ...]:
        exact = _merge_matches(
            _exact_matches(self.index.case_insensitive, text, preserve_case=False),
            _exact_matches(self.index.case_sensitive, text, preserve_case=True),
        )
        if exact or self.semantic_resolver is None:
            return tuple(exact)
        semantic = []
        for record in self.semantic_resolver(text):
            if isinstance(record, TermMatch):
                semantic.append(record)
            else:
                semantic.append(
                    _match_to_result(
                        record,
                        0,
                        len(text),
                        "semantic",
                        matched_text=text[:64],
                    )
                )
        return tuple(
            TermMatch(
                concept_id=item.concept_id,
                source_term=item.source_term,
                target_term=item.target_term,
                start=item.start,
                end=item.end,
                match_type="semantic",
                layer=item.layer,
                role=item.role,
                term_type=item.term_type,
                confidence=item.confidence or 0.0,
                do_not_translate=item.do_not_translate,
                forbidden_targets=item.forbidden_targets,
                matched_text=item.matched_text or "",
            )
            for item in semantic
        )


def matches_to_glossary(matches: Iterable[TermMatch]) -> dict[str, str]:
    """Build the legacy prompt dictionary from approved exact matches."""
    result: dict[str, str] = {}
    for match in matches:
        if match.match_type in {"exact", "alias"} and match.source_term not in result:
            result[match.source_term] = match.target_term
    return result
