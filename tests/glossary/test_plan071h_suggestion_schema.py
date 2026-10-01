# SPDX-License-Identifier: MPL-2.0
from qyunslation.glossary.suggestion_validate import validate_suggestion


def test_valid_suggestion():
    ok, reason = validate_suggestion(
        {
            "target": "特罗凯",
            "confidence": 0.9,
            "rationale": "approved alias",
            "domain": "oncology",
            "risk": "high",
            "source": "llm",
        }
    )
    assert ok and reason is None


def test_reject_missing_fields():
    ok, reason = validate_suggestion({"target": "x", "confidence": 0.5})
    assert not ok
    assert reason and reason.startswith("missing:")
