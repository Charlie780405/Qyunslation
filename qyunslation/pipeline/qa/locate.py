# SPDX-License-Identifier: MPL-2.0
"""PLAN-078b：把 QA 发现定位到页码或段落，并摘录原文，供人在对照视图里核对。

A finding's ``location`` is ``{"anchors": [...], "unlocatable_reason": str | None}``. Each anchor
names the document side (``source`` / ``translated``), a 1-based ``page`` when page text is
known (PDF) or a 1-based ``paragraph`` otherwise (Word / text), a short ``label`` (the value or
sentence at issue) and an ``excerpt`` of the surrounding text. Anchors never invent a place:
when a rule cannot say where, it returns none and the registry supplies the reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

MAX_ANCHORS = 8


@dataclass(frozen=True)
class Segment:
    """One non-empty line/paragraph of document text."""

    text: str
    page: int | None  # 1-based page when known
    index: int  # 1-based paragraph index within the page (page known) or the whole text


def segments_from_text(text: str | None) -> list[Segment]:
    out: list[Segment] = []
    for raw in (text or "").splitlines():
        if raw.strip():
            out.append(Segment(text=raw.strip(), page=None, index=len(out) + 1))
    return out


def segments_from_pages(pages: Iterable[str] | None) -> list[Segment]:
    out: list[Segment] = []
    for page_no, page_text in enumerate(pages or [], start=1):
        index = 0
        for raw in (page_text or "").splitlines():
            if raw.strip():
                index += 1
                out.append(Segment(text=raw.strip(), page=page_no, index=index))
    return out


def snippet(text: str, limit: int = 200) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def excerpt(text: str, start: int, end: int, radius: int = 60) -> str:
    """The text around ``text[start:end]``, flattened to one line and marked where it was cut."""
    lo, hi = max(0, start - radius), min(len(text), end + radius)
    flat = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return ("…" if lo > 0 else "") + flat + ("…" if hi < len(text) else "")


def anchor(side: str, segment: Segment | None, label: str, excerpt_text: str | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"side": side, "label": label}
    if segment is not None:
        if segment.page is not None:
            out["page"] = segment.page
            out["paragraph_on_page"] = segment.index
        else:
            out["page"] = None
            out["paragraph"] = segment.index
        out["excerpt"] = excerpt_text if excerpt_text is not None else snippet(segment.text)
    elif excerpt_text:
        out["excerpt"] = excerpt_text
    out.update(extra)
    return out


def page_anchor(side: str, page: int, label: str, excerpt_text: str | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"side": side, "page": page, "label": label}
    if excerpt_text:
        out["excerpt"] = excerpt_text
    out.update(extra)
    return out


def location(anchors: list[dict[str, Any]], reason: str | None = None) -> dict[str, Any]:
    if anchors:
        return {"anchors": anchors[:MAX_ANCHORS]}
    return {"anchors": [], **({"unlocatable_reason": reason} if reason else {})}


def find_segments(
    segments: Iterable[Segment], predicate: Callable[[Segment], bool], *, limit: int = 2
) -> list[Segment]:
    hits: list[Segment] = []
    for segment in segments:
        if predicate(segment):
            hits.append(segment)
            if len(hits) >= limit:
                break
    return hits
