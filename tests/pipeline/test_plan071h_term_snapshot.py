# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import pytest

from qyunslation.pipeline.term_snapshot import (
    build_term_snapshot,
    check_terms_in_translation,
    snapshot_is_consistent,
)
from qyunslation.persist.concept_repo import create_staging_concept
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base

SOURCE = "Patients received dupilumab and a generic placebo during the study."


@pytest.fixture()
def session():
    reset_engine()
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    from qyunslation.persist.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        reset_engine()


def _curated(session, source, target, *, term_type="general", forbidden=None):
    concept = create_staging_concept(
        session,
        preferred_source=source,
        preferred_target=target,
        term_type=term_type,
        layer="tenant",
        tenant_id="t1",
        forbidden=forbidden,
    )
    concept.status = "curated"
    session.commit()
    return concept


def _snap(session):
    return build_term_snapshot(session, tenant_id="t1", project_id=None, source_text=SOURCE)


def codes(findings):
    return {f.code: f.severity for f in findings}


def test_snapshot_is_ready_hashed_and_consistent(session):
    _curated(session, "placebo", "安慰剂")
    snap = _snap(session)
    assert snap["status"] == "ready"
    assert snap["match_count"] >= 1
    assert snap["termbase_version"]
    assert snapshot_is_consistent(snap)
    again = _snap(session)
    assert again["content_hash"] == snap["content_hash"]


def test_missing_normal_term_is_warning_and_present_is_clean(session):
    _curated(session, "placebo", "安慰剂")
    snap = _snap(session)
    assert codes(check_terms_in_translation(snap, "患者接受了赠剂。")) == {"TERM_TARGET_MISSING": "warning"}
    assert check_terms_in_translation(snap, "患者接受了安慰剂。") == []


def test_missing_high_risk_drug_is_blocker(session):
    _curated(session, "dupilumab", "度普利尤单抗", term_type="drug")
    snap = _snap(session)
    assert codes(check_terms_in_translation(snap, "患者接受了某药物。"))["TERM_HIGH_RISK_CONFLICT"] == "blocker"


def test_forbidden_target_is_blocker(session):
    _curated(session, "placebo", "安慰剂", forbidden=[("zh", "假药")])
    snap = _snap(session)
    found = codes(check_terms_in_translation(snap, "患者接受了安慰剂和假药。"))
    assert found["TERM_FORBIDDEN_TARGET"] == "blocker"


def test_tampered_snapshot_is_blocker(session):
    _curated(session, "placebo", "安慰剂")
    snap = _snap(session)
    snap["terms"][0]["preferred_target"] = "被篡改"
    assert not snapshot_is_consistent(snap)
    assert codes(check_terms_in_translation(snap, "安慰剂")) == {"TERM_SNAPSHOT_INCONSISTENT": "blocker"}


def test_pending_snapshot_is_not_consistent():
    assert not snapshot_is_consistent({"status": "snapshot_pending"})
