from __future__ import annotations

from qyunslation.glossary.resolver import (
    TermRecord,
    TermResolver,
    build_term_index,
    normalize_term,
)


def test_normalize_term_collapses_unicode_and_whitespace():
    assert normalize_term("  IL－4Rα\u3000agonist  ") == "il-4rα agonist"


def test_longest_match_wins_and_project_scope_overrides_clinical():
    resolver = TermResolver(
        build_term_index(
            [
                TermRecord(
                    concept_id="clinical",
                    source_term="primary endpoint",
                    target_term="主要终点",
                    layer="clinical",
                ),
                TermRecord(
                    concept_id="project",
                    source_term="primary endpoint",
                    target_term="主要疗效终点",
                    layer="project",
                ),
                TermRecord(
                    concept_id="long",
                    source_term="primary endpoint assessment",
                    target_term="主要终点评估",
                    layer="project",
                ),
            ]
        )
    )

    matches = resolver.resolve("The primary endpoint assessment was recorded.")

    assert len(matches) == 1
    assert matches[0].concept_id == "long"
    assert matches[0].target_term == "主要终点评估"
    assert matches[0].match_type == "exact"


def test_alias_and_abbreviation_are_exact_fast_path():
    calls: list[str] = []
    resolver = TermResolver(
        build_term_index(
            [
                TermRecord(
                    concept_id="gvhd",
                    source_term="graft-versus-host disease",
                    target_term="移植物抗宿主病",
                    layer="clinical",
                ),
                TermRecord(
                    concept_id="gvhd",
                    source_term="GVHD",
                    target_term="GVHD",
                    layer="clinical",
                    role="abbreviation",
                ),
            ]
        ),
        semantic_resolver=lambda text: calls.append(text) or [],
    )

    matches = resolver.resolve("GVHD was assessed after graft-versus-host disease.")

    assert [m.concept_id for m in matches] == ["gvhd", "gvhd"]
    assert all(m.match_type == "exact" for m in matches)
    assert calls == []


def test_unknown_term_uses_semantic_resolver_once_and_is_cached():
    calls: list[str] = []

    def semantic(text: str):
        calls.append(text)
        return [
            TermRecord(
                concept_id="drug",
                source_term="tralokinumab",
                target_term="tralokinumab",
                layer="project",
            )
        ]

    resolver = TermResolver(build_term_index([]), semantic_resolver=semantic)

    first = resolver.resolve("tralokinumab")
    second = resolver.resolve("tralokinumab")

    assert first[0].match_type == "semantic"
    assert second[0].match_type == "semantic"
    assert calls == ["tralokinumab"]


def test_word_boundary_prevents_partial_english_match():
    resolver = TermResolver(
        build_term_index(
            [
                TermRecord(
                    concept_id="ae",
                    source_term="adverse event",
                    target_term="不良事件",
                    layer="clinical",
                )
            ]
        )
    )

    assert resolver.resolve("adverse events") == []
