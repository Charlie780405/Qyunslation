# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：译前术语解析的确定性快路径和语义降级接口。

The resolver deliberately keeps the exact/alias path independent from the
embedding service.  A confirmed term should be resolved from the local index
on every subsequent translation; semantic search is only a fallback for text
that has no approved exact match.
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


def normalize_term(value: str) -> str:
    """Normalize a term without changing its human-readable representation."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.strip().split()).casefold()


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


class _TrieNode:
    __slots__ = ("children", "records")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.records: list[TermRecord] = []


def _record_key(record: TermRecord) -> tuple[int, int, str, str]:
    return (
        record.priority,
        1 if record.role == "preferred" else 0,
        len(record.normalized_source),
        record.concept_id,
    )


def build_term_index(records: Iterable[TermRecord]) -> _TrieNode:
    """Build a compact trie and discard duplicate lower-priority entries."""
    root = _TrieNode()
    by_key: dict[tuple[str, str, str, str], TermRecord] = {}
    for record in records:
        source = record.normalized_source
        if not source or not record.target_term.strip():
            continue
        key = (source, record.src_lang.casefold(), record.tgt_lang.casefold(), record.concept_id)
        previous = by_key.get(key)
        if previous is None or _record_key(record) > _record_key(previous):
            by_key[key] = record
    for record in by_key.values():
        node = root
        for char in record.normalized_source:
            node = node.children.setdefault(char, _TrieNode())
        node.records.append(record)
    for node in _walk_nodes(root):
        node.records.sort(key=_record_key, reverse=True)
    return root


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


def _match_to_result(record: TermRecord, start: int, end: int, match_type: str) -> TermMatch:
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
        confidence=1.0 if match_type == "exact" else 0.0,
        do_not_translate=record.do_not_translate,
        forbidden_targets=record.forbidden_targets,
    )


def _exact_matches(root: _TrieNode, text: str) -> list[TermMatch]:
    normalized = normalize_term(text)
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
        out.append(_match_to_result(record, cursor, end, "exact"))
        cursor = end
    return out


class TermResolver:
    """Resolve approved terms before translation, with a semantic fallback."""

    def __init__(
        self,
        index: _TrieNode,
        *,
        semantic_resolver: Callable[[str], Iterable[TermRecord | TermMatch]] | None = None,
        cache_size: int = 512,
    ) -> None:
        self.index = index
        self.semantic_resolver = semantic_resolver
        self._resolve_cached = lru_cache(maxsize=max(1, cache_size))(self._resolve_uncached)

    def resolve(self, text: str) -> list[TermMatch]:
        return list(self._resolve_cached(text or ""))

    def _resolve_uncached(self, text: str) -> tuple[TermMatch, ...]:
        exact = _exact_matches(self.index, text)
        if exact or self.semantic_resolver is None:
            return tuple(exact)
        semantic = []
        for record in self.semantic_resolver(text):
            if isinstance(record, TermMatch):
                semantic.append(record)
            else:
                semantic.append(_match_to_result(record, 0, len(text), "semantic"))
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
            )
            for item in semantic
        )


def matches_to_glossary(matches: Iterable[TermMatch]) -> dict[str, str]:
    """Build the legacy prompt dictionary from approved exact matches."""
    result: dict[str, str] = {}
    for match in matches:
        if match.match_type == "exact" and match.source_term not in result:
            result[match.source_term] = match.target_term
    return result
