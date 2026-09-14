from __future__ import annotations

from qyunslation.glossary.evaluation import evaluate_retrieval


def test_retrieval_score_counts_missing_predictions_as_misses():
    report = evaluate_retrieval(
        [
            {"source_term": "primary endpoint", "concept_id": "c1", "exact": True},
            {"source_term": "adverse event", "concept_id": "c2", "occurrences": 2},
        ],
        [
            {
                "source_term": "primary endpoint",
                "concept_id": "c1",
                "match_type": "exact",
                "confidence": 1.0,
            }
        ],
    )
    assert report["recall_at_5"] == 0.5
    assert report["occurrence_recall"] == 1 / 3
    assert report["top1_precision"] == 1.0
    assert report["high_confidence_coverage"] == 0.5
    assert report["exact_detection"] == 1.0


def test_retrieval_score_supports_alias_and_ordered_top_five():
    report = evaluate_retrieval(
        [{"source_term": "AE", "concept_id": "c2", "exact": True}],
        [
            {
                "source_term": "AE",
                "candidates": ["c9", "c2"],
                "match_type": "alias",
                "confidence": 0.9,
            }
        ],
    )
    assert report["recall_at_5"] == 1.0
    assert report["top1_precision"] == 0.0
    assert report["high_confidence_coverage"] == 1.0
    assert report["exact_detection"] == 1.0
