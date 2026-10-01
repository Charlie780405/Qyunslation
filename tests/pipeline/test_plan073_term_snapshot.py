# SPDX-License-Identifier: MPL-2.0
from qyunslation.pipeline.term_snapshot import build_term_snapshot, check_terms_in_translation


class _Match:
    concept_id = "c1"
    source_term = "PP"
    target_term = "符合方案集"
    term_type = "code"
    do_not_translate = False
    forbidden_targets = ()
    match_type = "exact"
    layer = "form"
    role = "preferred"
    confidence = 1.0
    start = 10
    end = 12
    matched_text = "PP"


class _Session:
    def __init__(self):
        self._terms = []

    def scalars(self, _stmt):
        return self

    def unique(self):
        return self

    def all(self):
        return self._terms

    def execute(self, _stmt):
        return []


def test_check_terms_skips_terms_without_source_hits(monkeypatch):
    monkeypatch.setattr(
        "qyunslation.pipeline.term_snapshot.resolve_runtime_terms",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "qyunslation.pipeline.term_snapshot.runtime_termbase_version",
        lambda *args, **kwargs: "058-test",
    )
    monkeypatch.setattr(
        "qyunslation.pipeline.term_snapshot.compile_term_policy",
        lambda matches, termbase_version=None: {"terms": []},
    )
    snapshot = build_term_snapshot(_Session(), tenant_id="t1", project_id=None, source_text="support pp")
    findings = check_terms_in_translation(snapshot, "support pp")
    assert findings == []
