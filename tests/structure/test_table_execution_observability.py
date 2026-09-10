"""PLAN-037 P1-A：表格执行保真 UI 摘要。"""
from __future__ import annotations

from types import SimpleNamespace

from qyunslation.structure.models import (
    ExecutionStatus,
    IssueSeverity,
    ManifestIssue,
    ObjectType,
    OutputEvidence,
    PipelineStage,
    Representation,
    TableObject,
)
from qyunslation.structure.table_execution_observability import (
    append_table_fidelity_hint,
    execution_table_fidelity_hint,
    scan_table_fidelity_hint,
    table_fidelity_payload,
)


def test_scan_hint_surfaces_continuation_unlinked():
    manifest = SimpleNamespace(
        issues=[
            ManifestIssue(
                code="TABLE_CONTINUATION_UNLINKED",
                severity=IssueSeverity.WARNING,
                stage=PipelineStage.SCAN,
                retryable=False,
                message="continued table has caption but no table region",
                details={"page": 7, "table": 1},
            )
        ],
        objects=[],
    )
    hint = scan_table_fidelity_hint(manifest)
    assert "TABLE_CONTINUATION_UNLINKED" in hint
    assert "第 7 页" in hint


def test_execution_hint_surfaces_digit_drift_and_preserved():
    manifest = SimpleNamespace(
        issues=[],
        objects=[
            TableObject.model_construct(
                type=ObjectType.TABLE,
                object_id="obj:" + "a" * 64,
                canvas_id="page:1",
                representation=Representation.NATIVE_TEXT,
                semantic_id="table:1",
                execution_status=ExecutionStatus.TRANSLATED,
                output_evidence=OutputEvidence(checks={"digits_preserved": True}),
                translatable_blocks=[],
            ),
            TableObject.model_construct(
                type=ObjectType.TABLE,
                object_id="obj:" + "b" * 64,
                canvas_id="page:2",
                representation=Representation.NATIVE_TEXT,
                semantic_id="table:2",
                execution_status=ExecutionStatus.FAILED_HARD,
                reason_code="table_digit_drift",
                output_evidence=OutputEvidence(
                    checks={"error": "TABLE_DIGIT_DRIFT:cell:0:1:0", "digits_preserved": False}
                ),
                translatable_blocks=[],
            ),
        ],
    )
    hint = execution_table_fidelity_hint(manifest)
    assert "digits_preserved" in hint
    assert "TABLE_DIGIT_DRIFT" in hint
    payload = table_fidelity_payload(manifest)
    assert payload["summary_text"]
    assert len(payload["execution"]) == 2


def test_append_table_fidelity_hint_preserves_base_summary():
    manifest = SimpleNamespace(
        issues=[
            ManifestIssue(
                code="TABLE_CONTINUATION_UNLINKED",
                severity=IssueSeverity.WARNING,
                stage=PipelineStage.SCAN,
                retryable=False,
                message="x",
                details={"page": 2, "table": 2},
            )
        ],
        objects=[],
    )
    merged = append_table_fidelity_hint("共 1 处表格。", manifest)
    assert merged.startswith("共 1 处表格")
    assert "TABLE_CONTINUATION_UNLINKED" in merged
