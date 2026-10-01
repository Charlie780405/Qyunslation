# SPDX-License-Identifier: MPL-2.0
from qyunslation.glossary.resolver import TermRecord, TermResolver, build_term_index


def test_pp_does_not_match_lowercase_pp_in_text():
    resolver = TermResolver(
        build_term_index(
            [
                TermRecord(
                    concept_id="pp-set",
                    source_term="PP",
                    target_term="符合方案集",
                    layer="form",
                    term_type="code",
                )
            ]
        )
    )
    matches = resolver.resolve("support pp. 123 and PP population")
    assert len(matches) == 1
    assert matches[0].matched_text == "PP"


def test_no_does_not_match_lowercase_no():
    resolver = TermResolver(
        build_term_index(
            [
                TermRecord(
                    concept_id="no-field",
                    source_term="No",
                    target_term="否",
                    layer="form",
                )
            ]
        )
    )
    matches = resolver.resolve("There is no evidence. Field No: 1")
    assert len(matches) == 1
    assert matches[0].matched_text == "No"
