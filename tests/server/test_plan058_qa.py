from __future__ import annotations

from types import SimpleNamespace

from qyunslation.server.core import _run_term_policy_qa


def _workflow(source: bytes, target: bytes, suffix: str = ".txt"):
    return SimpleNamespace(
        document_translated=SimpleNamespace(content=target, suffix=suffix),
        term_qa_source_content=None,
    )


def test_text_workflow_term_qa_is_a_formal_gate():
    policy = {
        "termbase_version": "058-v1",
        "terms": [
            {
                "concept_id": "c1",
                "source_term": "primary endpoint",
                "preferred_target": "主要终点",
                "hard_constraint": True,
            }
        ],
    }
    result = _run_term_policy_qa(
        _workflow(b"The primary endpoint.", "主要终点评估。"),
        fallback_source_content=b"The primary endpoint.",
        original_filename="input.txt",
        policy=policy,
    )
    assert result["available"] is True
    assert result["passed"] is True

    failed = _run_term_policy_qa(
        _workflow(b"The primary endpoint.", "主要终点评估。"),
        fallback_source_content=b"The primary endpoint.",
        original_filename="input.txt",
        policy={**policy, "terms": [{**policy["terms"][0], "preferred_target": "目标终点"}]},
    )
    assert failed["passed"] is False


def test_binary_writeback_reports_qa_unavailable_without_fake_pass():
    result = _run_term_policy_qa(
        _workflow(b"", b"PK\x03\x04", suffix=".docx"),
        fallback_source_content=b"PK\x03\x04",
        original_filename="input.docx",
        policy={"termbase_version": "058-v1", "terms": []},
    )
    assert result["available"] is False
    assert result["passed"] is True
    assert result["reason"] == "binary_or_unavailable_text_path"
