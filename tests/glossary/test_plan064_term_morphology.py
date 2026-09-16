# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：拒绝压制只打同形/更装饰变体，不误杀保留词干。"""
from qyunslation.glossary.term_morphology import (
    build_rejected_index,
    canonical_surface,
    is_rejected_source,
    morphology_stem,
)


def test_pending_suffix_and_prefix_canonicalize():
    assert canonical_surface("anti-tralokinumab-pending") == "anti-tralokinumab"
    assert canonical_surface("anti tralokinumab") == "anti-tralokinumab"
    assert morphology_stem("anti-tralokinumab-pending") == "tralokinumab"
    assert morphology_stem("IL-13") == "il-13"


def test_reject_prefixed_form_does_not_kill_keep_stem():
    index = build_rejected_index(["anti-tralokinumab-pending"])
    assert is_rejected_source("anti-tralokinumab-pending", index)
    assert is_rejected_source("anti-tralokinumab", index)
    assert is_rejected_source("anti tralokinumab", index)
    assert not is_rejected_source("tralokinumab", index)
    assert not is_rejected_source("IL-13", index)


def test_reject_bare_stem_suppresses_prefixed_variant():
    index = build_rejected_index(["tralokinumab"])
    assert is_rejected_source("tralokinumab", index)
    assert is_rejected_source("anti-tralokinumab", index)
    assert is_rejected_source("anti-tralokinumab-pending", index)
    assert not is_rejected_source("IL-13", index)
