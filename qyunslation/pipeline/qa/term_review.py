# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 阶段 C：本文术语风险（TERM_REVIEW_REQUIRED）与术语门禁开关。

Term *candidates* are vocabulary-governance work and no longer decide whether one document can be
delivered. What can block delivery is a document-level term risk, expressed as an ordinary C4 QA
item so it reuses the 078b disposition loop. A risk needs BOTH:

* a high-risk term type (drug, biologic, target, disease subtype, safety event, endpoint,
  scale, protocol) that is not already resolved from the approved lexicon; and
* concrete evidence, from signals that can be computed deterministically:
  ``multi_target``  the same source term was rendered two or more different ways in this document;
  ``alias_conflict`` the approved lexicon gives the same source term two different approved targets.

Signal b ("source term present, no target nor original in the translated paragraph") needs
paragraph alignment, which is model-based here (``workbench/term_align.py``), so it is not used as
a gate input (PLAN-079 §5.3 / WT-079).
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Iterable

from qyunslation.pipeline.qa import locate
from qyunslation.pipeline.qa.engine import QaFinding

CODE = "TERM_REVIEW_REQUIRED"
MAX_PER_DOCUMENT = 5
GATE_MODES = ("legacy", "shadow", "enforce")

# Both the English slugs of the deterministic path and the Chinese labels of the structured model path.
_REVIEW_TYPE_TOKENS = (
    "drug", "biologic", "target", "disease", "safety", "endpoint", "scale", "protocol",
    "药", "生物制品", "生物药", "靶", "基因", "蛋白", "受体", "细胞因子", "通路", "疾病", "安全", "终点", "量表", "方案",
)
_FINAL_STATUSES = frozenset({"approved", "rejected", "applied"})
_RESOLVED_MATCHES = frozenset({"termbase", "alias", "semantic", "exact"})


def term_gate_mode(raw: str | None = None) -> str:
    """``legacy`` (default) | ``shadow`` | ``enforce``; anything unrecognised falls back to legacy."""
    value = (raw if raw is not None else os.environ.get("QYUNSLATION_TERM_GATE_MODE") or "").strip().casefold()
    return value if value in GATE_MODES else "legacy"


def is_review_type(term_type: str | None) -> bool:
    folded = (term_type or "").casefold()
    return any(token in folded for token in _REVIEW_TYPE_TOKENS)


def _squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").casefold())


def distinct_targets(targets: Iterable[str]) -> list[str]:
    """Targets that really differ: "ASD" and "ASD（自闭症）" are one rendering, not two."""
    kept: list[tuple[str, str]] = []
    for raw in targets:
        key = _squash(raw)
        if not key:
            continue
        if any(key in other or other in key for other, _ in kept):
            continue
        kept.append((key, raw.strip()))
    return [raw for _, raw in kept]


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def review_required_findings(
    candidates: Iterable[Any], snapshot_terms: Iterable[dict[str, Any]] | None = None
) -> tuple[list[QaFinding], int]:
    """Return (findings, overflow). At most ``MAX_PER_DOCUMENT`` are returned; the rest are counted."""
    ranked: list[tuple[int, str, QaFinding]] = []

    grouped: dict[str, list[Any]] = defaultdict(list)
    for cand in candidates:
        if _get(cand, "status") in _FINAL_STATUSES or _get(cand, "match_type") in _RESOLVED_MATCHES:
            continue
        if not is_review_type(_get(cand, "term_type")):
            continue
        grouped[str(_get(cand, "source_norm") or "")].append(cand)
    for source_norm, rows in grouped.items():
        targets = distinct_targets(str(_get(r, "observed_target") or "") for r in rows)
        if not source_norm or len(targets) < 2:
            continue
        anchors: list[dict[str, Any]] = []
        for row in rows:
            for occ in _get(row, "occurrences", None) or []:
                page = _get(occ, "page_no")
                if page:
                    anchors.append(locate.page_anchor(
                        "source", int(page), str(_get(row, "source_term") or source_norm),
                        locate.snippet(str(_get(occ, "source_context") or ""), 160) or None,
                    ))
        label = str(_get(rows[0], "source_term") or source_norm)
        ranked.append((len(targets), source_norm, QaFinding(
            category="terminology", severity="blocker", code=CODE,
            message=f"同一术语在本文有 {len(targets)} 种译法：{label}",
            evidence={"source_norm": source_norm, "signal": "multi_target", "trigger": "TR-A",
                      "source_term": label, "targets": targets[:4]},
            location=locate.location(
                _dedupe_pages(anchors), "未能定位到具体页码，请按术语在全文中查找"),
        )))

    by_source: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    sources: dict[str, str] = {}
    for term in snapshot_terms or []:
        if not term.get("source_hits") or term.get("do_not_translate"):
            continue
        source = str(term.get("source_term") or "").strip()
        target = str(term.get("preferred_target") or "").strip()
        if source and target:
            key = source.casefold()
            sources[key] = source
            by_source[key][target].add(str(term.get("concept_id") or ""))
    for key, targets_map in by_source.items():
        targets = distinct_targets(targets_map)
        if len(targets) < 2:
            continue
        ranked.append((100, key, QaFinding(
            category="terminology", severity="blocker", code=CODE,
            message=f"术语库对同一原文有不同的批准译名：{sources[key]}",
            evidence={"source_norm": key, "signal": "alias_conflict", "trigger": "TR-C",
                      "source_term": sources[key], "targets": targets[:4]},
            location=locate.location([], "按术语库配置判定，不对应单一位置"),
        )))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    findings = [item[2] for item in ranked]
    return findings[:MAX_PER_DOCUMENT], max(0, len(findings) - MAX_PER_DOCUMENT)


def violation_findings(
    candidates: Iterable[Any], covered_blockers: Iterable[str] = ()
) -> list[QaFinding]:
    """One blocking ``TERM_TARGET_MISSING`` per approved hard-constraint term used inconsistently.

    A ``violation`` candidate means: in an aligned paragraph the source term occurs but the approved
    target does not. Once candidates stop gating delivery this signal must survive as a QA item; a
    term the document-level check (``term_snapshot``) already blocks on is not repeated.
    """
    covered = {str(item) for item in covered_blockers}
    grouped: dict[str, list[Any]] = defaultdict(list)
    for cand in candidates:
        if _get(cand, "status") == "violation":
            key = str(_get(cand, "concept_id") or f"candidate:{_get(cand, 'source_norm')}")
            grouped[key].append(cand)
    findings: list[QaFinding] = []
    for key, rows in sorted(grouped.items()):
        if key in covered:
            continue
        first = rows[0]
        label = str(_get(first, "source_term") or "")
        expected = str(_get(first, "suggested_target") or "")
        anchors: list[dict[str, Any]] = []
        for row in rows:
            for occ in _get(row, "occurrences", None) or []:
                page = _get(occ, "page_no")
                if page:
                    anchors.append(locate.page_anchor(
                        "source", int(page), label,
                        locate.snippet(str(_get(occ, "source_context") or ""), 160) or None,
                    ))
        findings.append(QaFinding(
            category="terminology", severity="blocker", code="TERM_TARGET_MISSING",
            message=f"批准译名未在对应段落出现：{label} → {expected}",
            evidence={"concept_id": key, "expected": expected, "source_hits": len(rows), "origin": "violation"},
            location=locate.location(_dedupe_pages(anchors), "未能定位到具体页码，请按术语在全文中查找"),
        ))
    return findings


def _dedupe_pages(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for anchor in anchors:
        page = anchor.get("page")
        if page in seen:
            continue
        seen.add(page)
        out.append(anchor)
    return out[:3]
