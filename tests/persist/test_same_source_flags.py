# SPDX-License-Identifier: MPL-2.0
"""同源多译 / 同源重复标记：只打标，不改数据。"""
from qyunslation.glossary.term_compliance import normalize_match_key, same_source_flags


def test_punctuation_variants_share_key():
    assert normalize_match_key("Jiangsu GenScend Biopharma Co., Ltd.") == normalize_match_key(
        "Jiangsu GenScend Biopharma Co. Ltd."
    )


def test_same_source_different_targets_is_conflict():
    flags = same_source_flags(
        [
            ("a", "GenScend", "江苏景行生物医药有限公司"),
            ("b", "GenScend", "景行生物"),
            ("c", "eczema", "湿疹"),
        ]
    )
    assert flags["a"]["code"] == "SAME_SOURCE_CONFLICT"
    assert flags["b"]["code"] == "SAME_SOURCE_CONFLICT"
    assert "c" not in flags


def test_same_source_same_target_is_duplicate():
    flags = same_source_flags(
        [
            ("x", "Jiangsu GenScend Biopharma Co., Ltd.", "江苏景行生物医药有限公司"),
            ("y", "Jiangsu GenScend Biopharma Co. Ltd.", "江苏景行生物医药有限公司"),
        ]
    )
    assert flags["x"]["code"] == "SAME_SOURCE_DUPLICATE"
    assert flags["y"]["code"] == "SAME_SOURCE_DUPLICATE"


def test_missing_target_or_source_not_flagged():
    flags = same_source_flags([("p", "GenScend", ""), ("q", "GenScend", None), ("r", "", "x")])
    assert flags == {}
