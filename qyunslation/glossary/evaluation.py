# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：术语检索金标指标，不依赖具体数据库或 embedding 服务。"""
from __future__ import annotations

from collections.abc import Iterable, Mapping


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def evaluate_retrieval(
    gold: Iterable[Mapping[str, object]],
    predictions: Iterable[Mapping[str, object]],
    *,
    high_confidence: float = 0.88,
) -> dict[str, float | int]:
    """Score Concept retrieval with recall, precision and coverage.

    Each gold row contains ``source_term``, ``concept_id`` and optionally
    ``occurrences``.  A prediction contains ``source_term``, a top-level
    ``concept_id`` or ``candidates`` (ordered Concept IDs), ``confidence`` and
    optionally ``match_type``.  Missing predictions count as misses, so a
    caller cannot inflate accuracy by omitting hard examples.
    """
    expected = {_normal(row.get("source_term")): row for row in gold}
    observed = {_normal(row.get("source_term")): row for row in predictions}
    if not expected:
        return {
            "gold_terms": 0,
            "recall_at_5": 1.0,
            "top1_precision": 1.0,
            "high_confidence_coverage": 1.0,
            "exact_detection": 1.0,
        }

    recall_hits = 0
    top1_count = 0
    top1_correct = 0
    high_conf_count = 0
    exact_expected = 0
    exact_hits = 0
    occurrences_expected = 0
    occurrences_hits = 0
    for source_norm, row in expected.items():
        concept_id = str(row.get("concept_id") or "")
        expected_occurrences = max(1, int(row.get("occurrences") or 1))
        occurrences_expected += expected_occurrences
        prediction = observed.get(source_norm)
        if prediction is None:
            continue
        candidates = prediction.get("candidates") or []
        if isinstance(candidates, str):
            candidates = [candidates]
        candidate_ids = [str(value) for value in candidates]
        top1 = str(prediction.get("concept_id") or (candidate_ids[0] if candidate_ids else ""))
        if concept_id in candidate_ids[:5] or top1 == concept_id:
            recall_hits += 1
            occurrences_hits += expected_occurrences
        if top1:
            top1_count += 1
            if top1 == concept_id:
                top1_correct += 1
        confidence = float(prediction.get("confidence") or 0.0)
        if confidence >= high_confidence:
            high_conf_count += 1
        match_type = str(prediction.get("match_type") or "").casefold()
        is_exact = bool(row.get("exact", False))
        if is_exact:
            exact_expected += 1
            if match_type in {"exact", "alias"}:
                exact_hits += 1

    return {
        "gold_terms": len(expected),
        "recall_at_5": recall_hits / len(expected),
        "occurrence_recall": occurrences_hits / occurrences_expected,
        "top1_precision": top1_correct / top1_count if top1_count else 0.0,
        "high_confidence_coverage": high_conf_count / len(expected),
        "exact_detection": exact_hits / exact_expected if exact_expected else 1.0,
    }
