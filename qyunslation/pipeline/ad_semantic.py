"""PLAN-076f: bounded semantic QA and one-shot repair contracts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Iterable

_RISK_MARKERS = re.compile(
    r"\b(?:dupilumab|tralokinumab|upadacitinib|abrocitinib|EASI(?:-75)?|SCORAD|IGA|PP-NRS|IL-\d+|mg|\d+%|no|not|without|must|may)\b"
    r"|特应性皮炎|湿疹|度普利尤单抗|不良事件|无|未|不得|必须|可以|剂量|终点",
    re.I,
)
_SEVERITIES = {"minor", "major", "critical"}
_CODES = {"TERM", "NUMBER", "NEGATION", "MODALITY", "ENDPOINT", "STRUCTURE"}


@dataclass(frozen=True)
class SemanticIssue:
    segment_id: str
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class RepairResult:
    target: str
    attempts: int
    repaired: bool
    fact_drift: bool = False


def select_high_risk_segments(segments: Iterable[dict], *, max_segments: int = 20) -> list[dict]:
    selected = [item for item in segments if _RISK_MARKERS.search(str(item.get("source") or ""))]
    return selected[:max_segments]


def parse_semantic_review(raw: str | dict) -> list[SemanticIssue]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        items = payload["items"]
        if not isinstance(items, list):
            raise ValueError
        result: list[SemanticIssue] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError
            severity, code = str(item.get("severity") or ""), str(item.get("code") or "")
            if severity not in _SEVERITIES or code not in _CODES:
                raise ValueError
            segment_id = str(item.get("id") or "").strip()
            message = str(item.get("message") or "").strip()
            if not segment_id or not message or len(message) > 1000:
                raise ValueError
            result.append(SemanticIssue(segment_id, severity, code, message))
        return result
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("semantic QA schema invalid") from exc


def _protected_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?\b|\b(?:mg|mL|EASI-75|SCORAD|IGA|PP-NRS)\b", text or "", flags=re.I))


def repair_once(
    *, source: str, target: str, issues: list[dict] | list[SemanticIssue], repair_fn: Callable[[str, str, list], str]
) -> RepairResult:
    if not issues:
        return RepairResult(target=target, attempts=0, repaired=False)
    candidate = repair_fn(source, target, issues)
    if not isinstance(candidate, str) or not candidate.strip():
        return RepairResult(target=target, attempts=1, repaired=False)
    protected = _protected_tokens(source)
    fact_drift = not protected.issubset(_protected_tokens(candidate))
    if fact_drift:
        return RepairResult(target=target, attempts=1, repaired=False, fact_drift=True)
    return RepairResult(target=candidate, attempts=1, repaired=candidate != target)
