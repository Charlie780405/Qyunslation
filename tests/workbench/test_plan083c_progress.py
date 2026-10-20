"""PLAN-083c：BabelDOC 之后的后处理阶段也要有可见进度（90–99%）。"""
from __future__ import annotations

import json
from pathlib import Path

from qyunslation.workbench import runner as r


def test_babel_progress_leaves_room_for_postprocess():
    assert r._scale_babel_progress(None) is None
    assert r._scale_babel_progress(0) == 0
    assert r._scale_babel_progress(50) == 45
    # BabelDOC 的 99% 不得越过后处理起点
    assert r._scale_babel_progress(99) < r.POSTPROCESS_PROGRESS_START


def _runner():
    obj = r.Pdf2zhRunner.__new__(r.Pdf2zhRunner)
    return obj


def test_report_postprocess_is_monotonic_and_clamped(tmp_path: Path):
    runner = _runner()
    path = tmp_path / "state.json"
    state = {"progress": 89, "stage": "export"}
    state = runner._report_postprocess(path, state, 93, "正在重排单语表格（1/2）")
    assert state["progress"] == 93 and state["stage"] == "table_figure"
    state = runner._report_postprocess(path, state, 91, "回退")
    assert state["progress"] == 93  # 不回退
    state = runner._report_postprocess(path, state, 500, "超界")
    assert state["progress"] == r.POSTPROCESS_PROGRESS_END
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["progress_message"] == "超界"


def test_run_table_figure_stage_reports_per_table(tmp_path: Path, monkeypatch):
    import sys
    import types

    from qyunslation.pipeline.events import StageEventBuffer
    from qyunslation.pipeline.stages import postprocess as pp
    from qyunslation.structure.models import ContentProfile, ObjectType

    seen: list[tuple[int, str]] = []
    mono = tmp_path / "a.zh.mono.pdf"
    mono.write_bytes(b"%PDF-1.4\n")

    class _Obj:
        type = ObjectType.TABLE
        semantic_id = "table:1"
        output_evidence = None
        execution_status = None
        reason_code = None

    class _Doc:
        content_profile = ContentProfile.RESEARCH_ARTICLE

    class _Manifest:
        objects = [_Obj(), _Obj()]
        document = _Doc()

    class _Scanner:
        def scan(self, _p):
            return _Manifest()

    def fake_translate(src, *, progress_cb=None, **_kw):
        for i in (1, 2):
            progress_cb(i, 2)
        return src

    fake = types.SimpleNamespace(translate_pdf_tables=fake_translate)
    monkeypatch.setattr(pp.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr("qyunslation.structure.scan_pdf.PdfStructureScanner", _Scanner)
    monkeypatch.setenv("QYUNSLATION_TABLE_POSTPROCESS", "literature")

    pp.run_table_figure_stage(
        mono_pdf=mono,
        dual_pdf=None,
        events=StageEventBuffer(),
        origin_pdf=mono,
        on_progress=lambda pct, msg: seen.append((pct, msg)),
    )
    assert [m for _p, m in seen] == ["正在重排单语表格（1/2）", "正在重排单语表格（2/2）"]
    assert seen[0][0] < seen[1][0] <= 95
