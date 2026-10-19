# SPDX-License-Identifier: MPL-2.0
"""Sentence lookup for term evidence: the complete sentence (between two sentence ends) around a term."""

from __future__ import annotations

import re
from typing import Any

# Sentence-final marks that always end a sentence.
_STRONG_END = "。！？!?；;"
_CLOSERS = "”\"')]）】"
# A full stop after these is not a sentence end: "e.g. the", "Fig. 3", "et al. reported".
_ABBREVIATIONS = frozenset({
    "e.g", "i.e", "vs", "fig", "figs", "dr", "mr", "mrs", "ms", "prof", "al", "no", "nos",
    "approx", "ca", "cf", "eq", "ref", "refs", "inc", "ltd", "co", "st", "vol", "pp", "sec", "ed",
})
# Smallest cap ever used when occurrence contexts were stored (older rows were cut at 1000 characters).
_STORED_CONTEXT_CAP = 1000
_STARTS_SENTENCE = re.compile(r"[A-Z0-9“\"'(\[（【\u4e00-\u9fff]")


def _is_sentence_end(text: str, index: int) -> bool:
    char = text[index]
    if char in _STRONG_END:
        return True
    if char != ".":
        return False
    tail = text[index + 1 :]
    if not tail:
        return True
    if not tail[0].isspace() and tail[0] not in _CLOSERS:
        return False  # 1.5 mg, a.b, URLs
    rest = tail.lstrip(_CLOSERS).lstrip()
    if not rest:
        return True
    word = re.search(r"([A-Za-z][A-Za-z.]*)$", text[:index])
    if word:
        token = word.group(1)
        if token.casefold().strip(".") in _ABBREVIATIONS or len(token.strip(".")) == 1:
            return False  # abbreviations and initials such as "Curtin P."
    return bool(_STARTS_SENTENCE.match(rest))


def sentence_bounds(text: str, start: int, end: int | None = None) -> tuple[int, int]:
    """Return ``(from, to)`` offsets of the sentence that contains ``text[start:end]``."""
    end = start if end is None else max(start, end)
    begin = 0
    for index in range(min(start, len(text)) - 1, -1, -1):
        if _is_sentence_end(text, index):
            begin = index + 1
            break
    finish = len(text)
    for index in range(min(end, len(text)), len(text)):
        if _is_sentence_end(text, index):
            finish = index + 1
            break
    while begin < finish and text[begin].isspace():
        begin += 1
    return begin, finish


def term_sentence(context: str, term: str, ordinal: int = 0) -> dict[str, Any]:
    """The complete sentence holding the ``ordinal``-th occurrence of ``term`` in ``context``.

    Returns ``sentence`` plus ``match_start``/``match_end`` (offsets inside ``sentence``, or ``None``
    when the term cannot be located again, e.g. it was normalised) and ``truncated``: True when the
    stored context was cut off in the middle of the sentence (contexts are stored with a length cap).
    """
    context = context or ""
    matches = list(re.finditer(re.escape(term), context, re.IGNORECASE)) if term else []
    if matches:
        match = matches[min(max(ordinal, 0), len(matches) - 1)]
        begin, finish = sentence_bounds(context, match.start(), match.end())
        position: tuple[int, int] | None = (match.start() - begin, match.end() - begin)
    else:
        begin, finish = sentence_bounds(context, 0, 0)
        position = None
    raw = context[begin:finish]
    sentence = raw.strip()
    if position is not None:
        shift = len(raw) - len(raw.lstrip())
        position = (position[0] - shift, position[1] - shift)
    ended = bool(sentence) and _is_sentence_end(sentence, len(sentence) - 1)
    return {
        "sentence": sentence,
        "match_start": position[0] if position else None,
        "match_end": position[1] if position else None,
        "truncated": len(context) >= _STORED_CONTEXT_CAP and finish >= len(context) and not ended,
    }
