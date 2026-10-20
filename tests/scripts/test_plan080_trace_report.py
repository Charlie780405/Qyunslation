# SPDX-License-Identifier: MPL-2.0
"""PLAN-080b：追踪报告对段落去向的分类。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

import plan080_trace_report as report  # noqa: E402


def _seen(pid: str, text: str, page: int = 1, length: int | None = None) -> dict:
    return {"event": "seen", "id": pid, "page": page, "length": length or len(text), "text": text}


def _run(tmp_path: Path, events: list[dict]) -> dict[str, str]:
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    out = tmp_path / "report.json"
    assert report.main([str(trace), "--json", str(out)]) == 0
    return {r["id"]: r["fate"] for r in json.loads(out.read_text(encoding="utf-8"))["paragraphs"]}


def test_fates_for_each_path(tmp_path):
    events = [
        _seen("a", "translated paragraph"),
        {"event": "sent", "id": "a"},
        {"event": "result", "id": "a", "same": False},
        _seen("b", "echoed paragraph"),
        {"event": "sent", "id": "b"},
        {"event": "result", "id": "b", "same": True},
        _seen("c", "url footnote"),
        {"event": "sent", "id": "c"},
        {"event": "fallback", "id": "c"},
        {"event": "result", "id": "c", "same": True},
        _seen("d", "lost paragraph"),
        {"event": "sent", "id": "d"},
        _seen("e", "tiny"),
        _seen("f", "123"),
        {"event": "skip", "id": "f", "reason": "numeric"},
    ]
    fates = _run(tmp_path, events)
    assert fates == {
        "a": "translated",
        "b": "unchanged",
        "c": "fallback_unchanged",
        "d": "sent_no_result",
        "e": "not_sent",
        "f": "skipped:numeric",
    }


def test_text_based_skip_is_joined_back_to_the_paragraph(tmp_path):
    """preserve 谓词只拿到文字、没有段落 ID，必须按节选关联，否则会被误判为 not_sent。"""
    text = "2. The protocol synopsis does not detail planned subgroup analyses."
    events = [
        _seen("p16", text),
        {"event": "skip", "id": None, "reason": "preserve", "text": text},
    ]
    assert _run(tmp_path, events) == {"p16": "skipped:preserve"}


def test_fallback_that_later_translates_counts_as_translated(tmp_path):
    events = [
        _seen("g", "needs the plain translator"),
        {"event": "sent", "id": "g"},
        {"event": "fallback", "id": "g"},
        {"event": "result", "id": "g", "same": False},
    ]
    assert _run(tmp_path, events) == {"g": "translated"}
