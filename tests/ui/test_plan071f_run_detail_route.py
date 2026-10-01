# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "frontend/src/next/router.js"
DETAIL = ROOT / "frontend/src/next/pages/RunDetailPage.vue"


def test_run_detail_route_split():
    router = ROUTER.read_text(encoding="utf-8")
    assert "RunDetailPage" in router
    assert "name: 'workbench-run'" in router
    detail = DETAIL.read_text(encoding="utf-8")
    assert "StageTimeline" in detail
    assert "legacy_unverified" in detail
    assert "pipeline: 'v2'" in detail
