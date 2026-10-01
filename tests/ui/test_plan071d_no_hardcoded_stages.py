# SPDX-License-Identifier: MPL-2.0
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = ROOT / "frontend/src/next/pages/WorkbenchPage.vue"


def test_workbench_uses_stage_timeline_not_forged_bucket():
    text = WORKBENCH.read_text(encoding="utf-8")
    assert "StageTimeline" in text
    assert "stageBucket" not in text
    assert "run.status === 'succeeded' && index < order.length" not in text
