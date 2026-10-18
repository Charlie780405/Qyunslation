"""PLAN-078b slice 2 end to end: what the API tells the reader about *where* a problem is."""
from __future__ import annotations

import pytest

from _plan078_flow import ADMIN, make_client, run_to_gate
from qyunslation.persist.db import reset_engine

pytest.importorskip("pymupdf")


def test_untranslated_pdf_points_at_the_pages_and_quotes_the_leftover_text(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "loc-untranslated")
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
        body = next(i for i in items if i["code"] == "UNTRANSLATED_BODY")
        anchors = body["location"]["anchors"]
        assert anchors, body["location"]
        first = anchors[0]
        assert first["side"] == "translated" and first["page"] == 1
        assert first["output_kind"] in {"mono", "dual"}
        assert "excerpt" in first and first["excerpt"]
        assert "body" not in body["location"].get("unlocatable_reason", "")
    reset_engine()


def test_every_item_either_has_a_place_or_says_why_not(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "loc-reasons")
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
        assert items
        for item in items:
            location = item["location"]
            assert location["anchors"] or location.get("unlocatable_reason"), (item["code"], location)
            for anchor in location["anchors"]:
                assert anchor["side"] in {"source", "translated"}
                assert anchor.get("page") or anchor.get("paragraph")
    reset_engine()
