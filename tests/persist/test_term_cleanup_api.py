# SPDX-License-Identifier: MPL-2.0
"""词库页：列表不截断、补译名、驳回/恢复、疑似不合规标记。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.glossary.term_compliance import assess_concept
from qyunslation.persist.concept_repo import (
    LIST_LIMIT_DEFAULT,
    concept_to_dict,
    create_staging_concept,
    list_concepts,
)
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, Concept

TERM_ADMIN = {"X-Dev-User": "alice", "X-Dev-Tenant": "t1", "X-Dev-Role": "term_admin"}
ADMIN = {"X-Dev-User": "root", "X-Dev-Tenant": "t1", "X-Dev-Role": "admin"}


@pytest.fixture()
def db(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    session = SessionLocal()
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as client:
        yield client, session
    session.close()
    reset_engine()


def _create(client, source, target, headers=TERM_ADMIN):
    response = client.post("/api/v1/concepts", json={"preferred_source": source, "preferred_target": target}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_list_is_not_capped_at_200(db):
    _client, session = db
    for index in range(LIST_LIMIT_DEFAULT // 8):  # 250 > old cap of 200
        create_staging_concept(session, preferred_source=f"term {index}", preferred_target=f"术语{index}")
    session.commit()
    assert LIST_LIMIT_DEFAULT > 200
    assert len(list_concepts(session)) == LIST_LIMIT_DEFAULT // 8 > 200


def test_compliance_flags_generic_phrases_but_keeps_drugs_and_abbreviations():
    cand = "document_term_candidate:abc;approved_by:x"
    assert assess_concept("sparse sampling", "稀疏采样", evidence=cand, term_type="量表/终点/方法")["code"] == "GENERIC_PHRASE"
    assert assess_concept("tralokinumab", "曲罗芦单抗", evidence=cand, term_type="药物") is None
    assert assess_concept("dupilumab", "度普利尤单抗", evidence=cand, term_type="general") is None
    assert assess_concept("PTMs", "翻译后修饰", evidence=cand, term_type="专业缩写") is None
    assert assess_concept("sensitivity analysis", "敏感性分析")["code"] == "PHRASE"
    assert assess_concept("", "江苏荃信生物医药有限公司")["code"] == "NO_SOURCE"
    assert assess_concept("2. Trial Design", "、试验设计 2")["code"] == "BROKEN_TARGET"
    assert assess_concept("validation endpoint 7478fd41", "验证终点评估", evidence=cand)["code"] == "TEST_JUNK"
    # 非候选来源的小写词不按泛用短语处理
    assert assess_concept("eczema", "湿疹") is None


def test_target_state_distinguishes_keep_source_from_missing(db):
    _client, session = db
    keep = Concept(domain="org", status="curated", version=1, do_not_translate=True, layer="org")
    missing = Concept(domain="org", status="curated", version=1, do_not_translate=False, layer="org")
    session.add_all([keep, missing])
    session.flush()
    from qyunslation.persist.models import ConceptTerm

    for concept, text in ((keep, "GSK"), (missing, "NewCo")):
        session.add(ConceptTerm(concept_id=concept.id, lang="en", text=text, normalized_text=text.lower(), role="preferred"))
    session.commit()
    session.refresh(keep)
    session.refresh(missing)
    assert concept_to_dict(keep)["target_state"] == "keep_source"
    assert concept_to_dict(missing)["target_state"] == "missing"


def test_patch_fills_missing_target_and_clears_keep_source(db):
    client, _session = db
    created = _create(client, "NewCo", "占位")
    response = client.patch(f"/api/v1/concepts/{created['id']}", json={"preferred_target": "新公司"}, headers=TERM_ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_state"] == "translated"
    assert [t["text"] for t in body["terms"] if t["lang"] == "zh" and t["role"] == "preferred"] == ["新公司"]
    assert body["version"] == created["version"] + 1


def test_reject_and_restore_are_audited_and_reversible(db):
    client, _session = db
    created = _create(client, "foo bar", "某某")
    rejected = client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "rejected", "note": "常用语"}, headers=TERM_ADMIN)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert "status:staging->rejected" in rejected.json()["evidence"]
    restored = client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "restore"}, headers=TERM_ADMIN)
    assert restored.json()["status"] == "staging"  # 回到驳回前，不是自动变成已批准
    noop = client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "restore"}, headers=TERM_ADMIN)
    assert noop.json()["status"] == "staging"
    assert client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "bogus"}, headers=TERM_ADMIN).status_code == 422
    assert client.patch(f"/api/v1/concepts/{created['id']}", json={}, headers=TERM_ADMIN).status_code == 422


def test_restore_returns_curated_terms_to_curated_and_unknown_to_staging(db):
    client, session = db
    curated = Concept(domain="clinical", status="curated", version=1, layer="org", tenant_id=None)
    legacy = Concept(domain="clinical", status="rejected", version=1, layer="org", tenant_id=None)
    session.add_all([curated, legacy])
    session.commit()
    assert client.patch(f"/api/v1/concepts/{curated.id}", json={"status": "rejected"}, headers=ADMIN).json()["status"] == "rejected"
    assert client.patch(f"/api/v1/concepts/{curated.id}", json={"status": "restore"}, headers=ADMIN).json()["status"] == "curated"
    # 没有留痕的旧驳回：回到待审核，绝不直接批准
    assert client.patch(f"/api/v1/concepts/{legacy.id}", json={"status": "restore"}, headers=ADMIN).json()["status"] == "staging"


def test_non_admin_cannot_patch_and_other_tenant_gets_404(db):
    client, _session = db
    created = _create(client, "secret", "密")
    translator = {"X-Dev-User": "t", "X-Dev-Tenant": "t1", "X-Dev-Role": "translator"}
    assert client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "rejected"}, headers=translator).status_code == 403
    other = {"X-Dev-User": "bob", "X-Dev-Tenant": "t2", "X-Dev-Role": "term_admin"}
    assert client.patch(f"/api/v1/concepts/{created['id']}", json={"status": "rejected"}, headers=other).status_code == 404


def test_global_concepts_need_admin_and_stay_visible_when_rejected(db):
    client, session = db
    shared = Concept(domain="clinical", status="curated", version=1, layer="clinical", tenant_id=None)
    session.add(shared)
    session.commit()
    path = f"/api/v1/concepts/{shared.id}"
    forbidden = client.patch(path, json={"status": "rejected"}, headers=TERM_ADMIN)
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "GLOBAL_CONCEPT_ADMIN_REQUIRED"
    assert client.patch(path, json={"status": "rejected"}, headers=ADMIN).status_code == 200
    listed = client.get("/api/v1/concepts", headers=TERM_ADMIN).json()
    assert [row["status"] for row in listed if row["id"] == shared.id] == ["rejected"]


def test_batch_status_skips_what_the_caller_may_not_touch(db):
    client, session = db
    own = _create(client, "alpha phrase", "甲")
    shared = Concept(domain="clinical", status="curated", version=1, layer="clinical", tenant_id=None)
    session.add(shared)
    session.commit()
    response = client.post(
        "/api/v1/concepts/batch-status",
        json={"ids": [own["id"], shared.id, "missing-id", own["id"]], "status": "rejected"},
        headers=TERM_ADMIN,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] == [own["id"]]
    assert {item["reason"] for item in body["skipped"]} == {"forbidden", "not_found"}
    again = client.post("/api/v1/concepts/batch-status", json={"ids": [own["id"]], "status": "rejected"}, headers=TERM_ADMIN).json()
    assert again["changed"] == [] and again["unchanged"] == [own["id"]]
