"""PLAN-078d: server-side search, filters, grouping and stable pagination of the task list."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from _plan078d_seed import (
    ADMIN, BASE_TIME, OTHER, OTHER_TENANT, OWNER, REVIEWER,
    collect_all, get_items, make_app, seed_run, tenant_id,
)
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine


@pytest.fixture()
def client(monkeypatch, tmp_path):
    with make_app(monkeypatch, tmp_path) as current:
        yield current
    reset_engine()


def _seed(client, specs, headers=OWNER):
    tenant = tenant_id(client, headers)
    ids = []
    with persist_db.SessionLocal() as session:
        for spec in specs:
            ids.append(seed_run(session, tenant, **spec).id)
        session.commit()
    return ids


# --- more than 100 tasks stay reachable ------------------------------------------------------------


def test_every_one_of_250_tasks_is_reachable_exactly_once(client):
    _seed(client, [{"name": f"任务 {i:03d}", "filename": f"file-{i:03d}.pdf"} for i in range(250)])
    ids = collect_all(client, page_size=100)
    assert len(ids) == 250 and len(set(ids)) == 250
    first = get_items(client, page_size=100)
    assert first["total"] == 250 and len(first["items"]) == 100 and first["next_cursor"]


def test_page_size_is_capped_and_defaults_stay_compatible(client):
    _seed(client, [{"name": f"t{i}"} for i in range(3)])
    assert client.get("/api/v1/translation-runs?page_size=101", headers=OWNER).status_code == 422
    legacy = client.get("/api/v1/translation-runs", headers=OWNER).json()
    assert len(legacy["items"]) == 3  # old callers still get a plain list in "items"


def test_pagination_is_stable_with_identical_timestamps_and_new_rows_arriving(client):
    same = BASE_TIME
    _seed(client, [{"name": f"同一时刻 {i}", "created": same, "updated": same} for i in range(30)])
    page1 = get_items(client, page_size=10)
    cursor = page1["next_cursor"]
    _seed(client, [{"name": "新来的", "created": same + timedelta(hours=5)}])  # newer than everything seen
    rest = []
    while cursor:
        page = get_items(client, page_size=10, cursor=cursor)
        rest.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
    seen = [i["id"] for i in page1["items"]] + rest
    assert len(seen) == 30 and len(set(seen)) == 30  # no row twice, none skipped


# --- search ------------------------------------------------------------------------------------------


def test_search_matches_task_name_original_file_name_and_id_prefix(client):
    ids = _seed(
        client,
        [
            {"name": "阿尔法方案", "filename": "protocol-A.pdf"},
            {"name": None, "filename": "Beta_Regulatory.docx"},
            {"name": "第三个", "filename": "misc.pdf"},
        ],
    )
    assert [i["id"] for i in get_items(client, q="阿尔法")["items"]] == [ids[0]]
    assert [i["id"] for i in get_items(client, q="beta_regulatory")["items"]] == [ids[1]]  # file name, any case
    assert [i["id"] for i in get_items(client, q="PROTOCOL-a")["items"]] == [ids[0]]
    assert [i["id"] for i in get_items(client, q=ids[2][:8])["items"]] == [ids[2]]
    assert get_items(client, q="不存在的名字")["items"] == []


def test_search_treats_percent_and_underscore_as_plain_text(client):
    ids = _seed(client, [{"name": "100% 完成"}, {"name": "a_b"}, {"name": "axb"}])
    assert [i["id"] for i in get_items(client, q="100%")["items"]] == [ids[0]]
    assert [i["id"] for i in get_items(client, q="a_b")["items"]] == [ids[1]]


def test_a_renamed_task_is_found_by_its_new_name_and_its_original_file_name(client):
    ids = _seed(client, [{"name": None, "filename": "original-upload.pdf"}])
    assert client.patch(f"/api/v1/translation-runs/{ids[0]}", headers=OWNER, json={"display_name": "给客户的最终版"}).status_code == 200
    assert [i["id"] for i in get_items(client, q="最终版")["items"]] == ids
    assert [i["id"] for i in get_items(client, q="original-upload")["items"]] == ids


# --- filters, sort, facets --------------------------------------------------------------------------------


def test_filters_by_state_format_direction_domain_and_dates(client):
    ids = _seed(
        client,
        [
            {"name": "a", "status": "gated", "quality": "qa_blocked", "filename": "a.pdf", "domain": "ad", "created": BASE_TIME},
            {"name": "b", "status": "gated", "quality": "review_ready", "filename": "b.docx", "created": BASE_TIME + timedelta(days=10)},
            {"name": "c", "status": "succeeded", "quality": "approved", "filename": "c.pdf", "direction": "简体中文 → English", "created": BASE_TIME + timedelta(days=20)},
            {"name": "d", "status": "failed", "quality": "draft", "filename": "d.pdf", "created": BASE_TIME + timedelta(days=30)},
        ],
    )
    names = lambda **p: sorted(i["display_name"] for i in get_items(client, **p)["items"])  # noqa: E731
    assert names(lifecycle="qa_action") == ["a"]
    assert names(lifecycle="qa_action,review") == ["a", "b"]  # comma separated
    assert sorted(i["display_name"] for i in client.get("/api/v1/translation-runs?lifecycle=completed&lifecycle=failed", headers=OWNER).json()["items"]) == ["c", "d"]
    assert names(format="docx") == ["b"]
    assert names(direction="简体中文 → English") == ["c"]
    assert names(domain="ad") == ["a"]
    d = (BASE_TIME + timedelta(days=10)).date().isoformat()
    assert names(created_from=d, created_to=d) == ["b"]  # the end date is inclusive
    assert names(created_from=(BASE_TIME + timedelta(days=15)).date().isoformat()) == ["c", "d"]
    assert get_items(client, lifecycle="no_such_phase")["items"] == []


def test_archived_filter_and_legacy_parameters(client):
    _seed(client, [{"name": "live"}, {"name": "old", "archived": True}, {"name": "broken", "status": "failed", "quality": "draft"}])
    names = lambda **p: sorted(i["display_name"] for i in get_items(client, **p)["items"])  # noqa: E731
    assert names() == ["broken", "live"]  # archived tasks are hidden by default
    assert names(archived="archived") == ["old"]
    assert names(archived="all") == ["broken", "live", "old"]
    assert names(include_archived="true") == ["broken", "live", "old"]  # legacy
    assert names(status="failed") == ["broken"]  # legacy


def test_sort_by_name_updated_and_created_in_both_directions(client):
    _seed(
        client,
        [
            {"name": "banana", "created": BASE_TIME + timedelta(days=1), "updated": BASE_TIME + timedelta(days=9)},
            {"name": "Apple", "created": BASE_TIME + timedelta(days=2), "updated": BASE_TIME + timedelta(days=8)},
            {"name": "cherry", "created": BASE_TIME + timedelta(days=3), "updated": BASE_TIME + timedelta(days=7)},
        ],
    )
    names = lambda **p: [i["display_name"] for i in get_items(client, **p)["items"]]  # noqa: E731
    assert names() == ["cherry", "Apple", "banana"]  # newest created first
    assert names(sort="created", order="asc") == ["banana", "Apple", "cherry"]
    assert names(sort="updated") == ["banana", "Apple", "cherry"]
    assert names(sort="name", order="asc") == ["Apple", "banana", "cherry"]  # case-insensitive
    assert names(sort="name", order="desc") == ["cherry", "banana", "Apple"]
    assert len(collect_all(client, page_size=2, sort="name", order="asc")) == 3  # cursors work for every sort


def test_totals_and_facets_describe_the_filtered_list(client):
    _seed(
        client,
        [{"name": f"b{i}", "quality": "qa_blocked"} for i in range(3)]
        + [{"name": f"r{i}", "quality": "review_ready"} for i in range(2)]
        + [{"name": "done", "status": "succeeded", "quality": "approved"}],
    )
    page = get_items(client, lifecycle="qa_action", page_size=2)
    assert page["total"] == 3 and len(page["items"]) == 2 and page["next_cursor"]
    assert page["facets"]["lifecycle"] == {"qa_action": 3, "review": 2, "completed": 1}  # ignores the lifecycle filter itself
    assert page["facets"]["total"] == 6


# --- versions ---------------------------------------------------------------------------------------------------


def test_versions_of_one_task_are_grouped_under_the_newest(client):
    from qyunslation.persist.models import PreflightRecord

    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        v1 = seed_run(session, tenant, name="方案", status="gated", quality="qa_blocked")
        pf = session.get(PreflightRecord, v1.preflight_id)
        v2 = seed_run(session, tenant, name="方案", status="gated", quality="review_ready", generation=2, preflight=pf)
        v3 = seed_run(session, tenant, name="方案", status="succeeded", quality="approved", generation=3, preflight=pf)
        other = seed_run(session, tenant, name="另一个")
        session.commit()
        ids = (v1.id, v2.id, v3.id, other.id)
    grouped = get_items(client)
    assert sorted(i["id"] for i in grouped["items"]) == sorted([ids[2], ids[3]])
    newest = next(i for i in grouped["items"] if i["id"] == ids[2])
    assert newest["generation"] == 3 and newest["version_count"] == 3 and newest["lifecycle"] == "completed"
    assert grouped["total"] == 2
    assert grouped["facets"]["lifecycle"].get("qa_action", 0) == 0  # an old blocked version is not today's state
    flat = get_items(client, group_versions="false")
    assert len(flat["items"]) == 4 and flat["total"] == 4
    versions = client.get(f"/api/v1/translation-runs/{ids[2]}/versions", headers=OWNER).json()["items"]
    assert [v["generation"] for v in versions] == [1, 2, 3]
    assert [v["id"] for v in versions] == [ids[0], ids[1], ids[2]]
    assert versions[0]["superseded_by"] == ids[1] and versions[2]["superseded_by"] is None


# --- who sees what ---------------------------------------------------------------------------------------------


def test_visibility_follows_role_and_tenant(client):
    _seed(client, [{"name": "owner-task", "actor": "owner1"}], headers=OWNER)
    other_tenant_id = tenant_id(client, OTHER_TENANT)
    with persist_db.SessionLocal() as session:
        seed_run(session, other_tenant_id, name="elsewhere", actor="owner1")
        session.commit()
    assert [i["display_name"] for i in get_items(client, OWNER)["items"]] == ["owner-task"]
    assert get_items(client, OTHER)["items"] == []  # another translator sees nothing of it
    assert [i["display_name"] for i in get_items(client, REVIEWER)["items"]] == ["owner-task"]
    assert [i["display_name"] for i in get_items(client, ADMIN)["items"]] == ["owner-task"]
    assert [i["display_name"] for i in get_items(client, OTHER_TENANT)["items"]] == ["elsewhere"]
    assert get_items(client, OTHER)["total"] == 0


# --- the list does not do work for rows that cannot change -------------------------------------------------


def test_only_rows_that_can_still_change_are_refreshed(client, monkeypatch):
    _seed(client, [{"name": f"settled{i}", "status": "gated", "quality": "review_ready"} for i in range(20)]
          + [{"name": "failed", "status": "failed", "quality": "draft"}, {"name": "cancelled", "status": "cancelled", "quality": "draft"}])
    _seed(client, [{"name": "running", "status": "translating", "quality": "draft"}])
    calls = []
    real = api_v1_module._refresh_translation_run

    def spy(session, run):
        calls.append(run.display_name)
        return real(session, run)

    monkeypatch.setattr(api_v1_module, "_refresh_translation_run", spy)
    get_items(client)
    assert calls == ["running"]  # settled rows are not poked on every poll


def test_query_count_does_not_grow_with_the_number_of_rows(client):
    def count_statements(rows):
        _seed(client, [{"name": f"r{rows}-{i}", "quality": "qa_blocked"} for i in range(rows)])
        statements = []

        def before(conn, cursor, statement, *a, **k):
            statements.append(statement)

        engine = persist_db.get_engine()
        event.listen(engine, "before_cursor_execute", before)
        try:
            get_items(client, page_size=100)
        finally:
            event.remove(engine, "before_cursor_execute", before)
        return len(statements)

    small = count_statements(5)
    large = count_statements(60)  # now 65 rows in the list
    assert large <= small + 3, (small, large)


def test_a_list_of_250_stays_fast(client):
    import time

    _seed(client, [{"name": f"任务 {i}", "quality": "qa_blocked" if i % 3 == 0 else "review_ready"} for i in range(250)])
    started = time.perf_counter()
    get_items(client, page_size=100)
    assert time.perf_counter() - started < 1.5  # generous on CI hardware; the real bound is measured on PG
