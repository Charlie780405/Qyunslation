# SPDX-License-Identifier: MPL-2.0
"""PLAN-060：译后证据不得把参考文献伪装成术语候选。"""
from __future__ import annotations

from PIL import Image

from qyunslation.workbench.gui_client import build_bilingual_evidence
from qyunslation.workbench.evidence import BilingualTermEvidence, extract_term_pairs


def test_explicit_table_and_ocr_term_evidence_keeps_locator():
    rows = extract_term_pairs(
        [
            BilingualTermEvidence(
                source_text="Primary endpoint",
                target_text="主要终点",
                source_term="primary endpoint",
                target_term="主要终点",
                role="table",
                page_no=3,
                block_id="table-1-r2-c1",
                object_id="table-1",
            ),
            BilingualTermEvidence(
                source_text="ABC-101",
                target_text="ABC-101",
                source_term="ABC-101",
                target_term="ABC-101",
                role="ocr",
                page_no=4,
                object_id="figure-2",
            ),
        ]
    )

    assert [row["source_term"] for row in rows] == ["primary endpoint", "ABC-101"]
    assert rows[0]["occurrences"][0]["block_id"] == "table-1-r2-c1"
    assert rows[1]["occurrences"][0]["object_id"] == "figure-2"


def test_reference_evidence_is_never_extracted_as_a_candidate():
    rows = extract_term_pairs(
        [
            BilingualTermEvidence(
                source_text="ABC-101", target_text="ABC-101", role="reference"
            )
        ]
    )
    assert rows == []


def test_unaligned_code_candidate_does_not_fabricate_a_target_translation():
    rows = extract_term_pairs(
        [BilingualTermEvidence(source_text="ABC-101 was administered.", target_text="已给药。")]
    )
    assert rows == [
        {
            "source_term": "ABC-101",
            "observed_target": "",
            "term_type": "general",
            "source_context": "ABC-101 was administered.",
            "target_context": "已给药。",
            "occurrences": [
                {
                    "page_no": None,
                    "block_id": None,
                    "object_id": None,
                    "char_start": None,
                    "char_end": None,
                    "bbox": None,
                    "source_context": "ABC-101 was administered.",
                    "target_context": "已给药。",
                }
            ],
        }
    ]


def test_image_ocr_evidence_requires_geometric_alignment(monkeypatch, tmp_path):
    source, target = tmp_path / "source.png", tmp_path / "target.png"
    Image.new("RGB", (200, 100), "white").save(source)
    Image.new("RGB", (200, 100), "white").save(target)

    def fake_ocr(path):
        if str(path) == str(source):
            return [(10, 10, 90, 30, "Primary endpoint", 0.99)]
        return [(12, 10, 90, 30, "主要终点", 0.99)]

    monkeypatch.setattr("qyunslation.extensions.image_translate.ocr_image", fake_ocr)
    rows, reason = build_bilingual_evidence(source, target)

    assert reason is None
    assert len(rows) == 1
    assert rows[0].role == "ocr"
    assert rows[0].source_term == "Primary endpoint"
    assert rows[0].target_term == "主要终点"
