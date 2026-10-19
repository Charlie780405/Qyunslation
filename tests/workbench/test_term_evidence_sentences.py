# SPDX-License-Identifier: MPL-2.0
"""Term evidence shows every occurrence with the complete sentence around the term."""

from __future__ import annotations

from types import SimpleNamespace

from qyunslation.workbench.sentences import sentence_bounds, term_sentence

PARAGRAPH = (
    "The sponsor ran 3 trials. Jiangsu proposed adding relevant primary analysis subgroup analyses "
    "for the primary endpoint (e.g. age, sex). The dose was 1.5 mg daily, see Fig. 3 for details! "
    "Were subgroup analyses pre-specified? Curtin P. et al. reported no change."
)


def test_sentence_is_the_text_between_two_sentence_ends():
    result = term_sentence(PARAGRAPH, "subgroup analyses", 0)
    assert result["sentence"] == (
        "Jiangsu proposed adding relevant primary analysis subgroup analyses for the primary endpoint (e.g. age, sex)."
    )
    assert result["sentence"][result["match_start"] : result["match_end"]].casefold() == "subgroup analyses"
    assert result["truncated"] is False


def test_the_nth_occurrence_gets_its_own_sentence():
    second = term_sentence(PARAGRAPH, "subgroup analyses", 1)
    assert second["sentence"] == "Were subgroup analyses pre-specified?"


def test_decimals_abbreviations_and_initials_do_not_split():
    text = "The dose was 1.5 mg daily, see Fig. 3 for details! Next."
    begin, end = sentence_bounds(text, text.index("daily"))
    assert text[begin:end] == "The dose was 1.5 mg daily, see Fig. 3 for details!"
    author = "Curtin P. et al. reported no change. Later."
    begin, end = sentence_bounds(author, author.index("change"))
    assert author[begin:end] == "Curtin P. et al. reported no change."


def test_chinese_sentences_and_a_missing_term():
    text = "第一句话。对亚组分析进行了预设。第三句话。"
    assert term_sentence(text, "亚组分析", 0)["sentence"] == "对亚组分析进行了预设。"
    missing = term_sentence("Only one sentence here. Another.", "not present", 0)
    assert missing["sentence"] == "Only one sentence here."
    assert missing["match_start"] is None


def test_a_cut_off_context_is_flagged():
    cut = ("word " * 250) + "subgroup analyses and the sentence never ends"
    assert term_sentence(cut, "subgroup analyses")["truncated"] is True


def test_candidate_payload_lists_every_occurrence_with_its_sentence():
    from qyunslation.persist.candidate_repo import candidate_to_dict

    def occurrence(index: int, start: int):
        return SimpleNamespace(
            id=f"occ-{index}", page_no=index + 1, block_id="paragraph:1" if index < 2 else f"paragraph:{index}",
            object_id=None, char_start=start, char_end=start + 17, bbox=None,
            source_context=PARAGRAPH if index < 2 else f"Extra {index}. The subgroup analyses were repeated in part {index}.",
            target_context="译文",
        )

    candidate = SimpleNamespace(
        id="cand", job_id=None, tenant_id="t", project_id=None, source_sha256=None, src_lang="en", tgt_lang="zh",
        source_term="subgroup analyses", source_norm="subgroup analyses", observed_target=None, suggested_target=None,
        term_type="general", risk="normal", status="pending", match_type=None, confidence=None, concept_id=None,
        termbase_version=None, source_context=PARAGRAPH[:100], target_context=None, extraction_metadata={},
        reviewed_by=None, reviewed_at=None, decision_note=None, version=1, created_at=None, updated_at=None,
        occurrences=[occurrence(0, 85), occurrence(1, 170), occurrence(2, 900), occurrence(3, 1200)],
        decisions=[],
    )
    payload = candidate_to_dict(candidate)
    assert payload["occurrence_count"] == 4
    sentences = [row["sentence"] for row in payload["occurrences"]]
    assert len(sentences) == 4
    assert sentences[0].startswith("Jiangsu proposed adding")
    assert sentences[1] == "Were subgroup analyses pre-specified?"
    assert sentences[2] == "The subgroup analyses were repeated in part 2."
    assert sentences[3] == "The subgroup analyses were repeated in part 3."


# --- extraction: a sentence continues over PDF line breaks --------------------------------------

LINES = """Dupilumab for a patient with severe atopic dermatitis
Patricia Curtin BS, Jessica Gai BA, MS, Michael Dans MD
1 Department of Dermatology, New York Medical College, Valhalla, NY 10595
Jiangsu proposed treating patients with vitiligo and severe atopic dermatitis in the
primary efficacy cohort and asked if it is acceptable. The Agency had no objection to
vitiligo patients.
References
Curtin P. Vitiligo case report. 2024;10:1-2.
"""


def test_extraction_stitches_the_sentence_over_line_breaks_and_skips_excluded_lines():
    from qyunslation.workbench.term_extract import discover_term_occurrences

    rows = {row["source_norm"]: row for row in discover_term_occurrences(LINES, "")}
    contexts = [occurrence["source_context"] for occurrence in rows["vitiligo"]["occurrences"]]
    assert contexts == [
        "Jiangsu proposed treating patients with vitiligo and severe atopic dermatitis in the primary efficacy cohort and asked if it is acceptable.",
        "The Agency had no objection to vitiligo patients.",
    ]
    assert not any("Curtin" in context or "Valhalla" in context for context in contexts)


def test_a_recheck_refreshes_the_stored_context_instead_of_duplicating_the_occurrence():
    from qyunslation.persist.candidate_repo import enqueue_candidate
    from qyunslation.persist.models import Base, Job, Project, Tenant
    from qyunslation.persist import db as persist_db
    from qyunslation.persist.db import init_engine, reset_engine

    reset_engine()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = persist_db.SessionLocal()
    try:
        tenant = Tenant(slug="t-sent", name="T")
        session.add(tenant)
        session.flush()
        project = Project(tenant_id=tenant.id, slug="p", name="P")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="b" * 64, status="completed")
        session.add(job)
        session.flush()
        place = {"page_no": None, "block_id": "paragraph:3", "char_start": 10, "char_end": 27, "bbox": None}

        def enqueue(context):
            return enqueue_candidate(
                session, job=job, tenant_id=tenant.id, project_id=project.id, source_term="subgroup analyses",
                observed_target=None, suggested_target=None, term_type="general", risk="normal",
                occurrences=[{**place, "source_context": context, "target_context": "译文"}],
            )

        first = enqueue("for the primary")
        second = enqueue("Jiangsu proposed adding subgroup analyses for the primary efficacy endpoint.")
        assert first.id == second.id
        assert len(second.occurrences) == 1
        assert second.occurrences[0].source_context.endswith("efficacy endpoint.")
        enqueue("Another place entirely.")  # same position, still no duplicate
        assert len(second.occurrences) == 1
    finally:
        session.close()
        reset_engine()
