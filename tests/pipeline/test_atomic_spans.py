# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：原子 span 与后处理策略测试。"""
from __future__ import annotations

from qyunslation.pipeline.atomic_spans import (
    restore_atomic_spans,
    shield_atomic_spans,
    strip_ordinal_artifacts,
)
from qyunslation.pipeline.events import StageEventBuffer
from qyunslation.pipeline.stages.postprocess import (
    low_confidence_image_policy,
    mark_preserve_objects,
    run_layout_stage,
    run_table_figure_stage,
    table_overflow_fallback_chain,
)
from qyunslation.pipeline.stages import build_minimal_manifest
from qyunslation.structure.models import PreserveKind, ObjectType, ImageObject, Representation


def test_email_url_pind_reference_shield_and_restore():
    src = (
        "Contact jane.doe@fda.hhs.gov or www.fda.gov. "
        "PIND 123456 Reference ID: 5864277 on the 20th floor."
    )
    shielded = shield_atomic_spans(src)
    assert "jane.doe@fda.hhs.gov" not in shielded.text
    assert "www.fda.gov" not in shielded.text
    assert "PIND 123456" not in shielded.text
    assert "Reference ID: 5864277" not in shielded.text
    assert "20th" not in shielded.text
    assert "⟦QYSPAN:" in shielded.text
    # Simulate MT that keeps tokens
    restored = shielded.restore(shielded.text)
    assert "jane.doe@fda.hhs.gov" in restored
    assert "www.fda.gov" in restored
    assert "PIND 123456" in restored
    assert "Reference ID: 5864277" in restored
    assert "20th" in restored


def test_restore_strips_th_artifacts():
    spans = shield_atomic_spans("the 20th day").spans
    dirty = "the 20^{th} day"
    # even without token, cleaner removes artifact
    assert "^{th}" not in strip_ordinal_artifacts(dirty)
    assert "^{th}" not in restore_atomic_spans(dirty, spans)


def test_overflow_chain_order():
    assert table_overflow_fallback_chain()[0] == "wrap"
    assert table_overflow_fallback_chain()[-1] == "image_fallback"


def test_low_confidence_keeps_original():
    assert low_confidence_image_policy(0.2) == "keep_original_warn"
    assert low_confidence_image_policy(0.9) == "translate_labels"


def test_mark_preserve_sets_policy():
    manifest = build_minimal_manifest(
        source_sha256="b" * 64, source_name="x.pdf", source_format="pdf"
    )
    # Inject a logo image object
    from qyunslation.structure.models import build_object_id, SourceRef, SourceRefKind, ExecutionStatus

    oid = build_object_id(
        "b" * 64,
        "page:1",
        ObjectType.IMAGE,
        "logo:1",
        [{"kind": "GENERATED_ASSET", "ref": "logo:1"}],
    )
    logo = ImageObject(
        type=ObjectType.IMAGE,
        object_id=oid,
        canvas_id="page:1",
        representation=Representation.BITMAP,
        source_refs=[SourceRef(kind=SourceRefKind.GENERATED_ASSET, ref="logo:1")],
        execution_status=ExecutionStatus.PENDING,
        preserve_kind=PreserveKind.LOGO,
        source_object_hash="c" * 64,
        translatable_blocks=[],
    )
    manifest.objects.append(logo)
    assert mark_preserve_objects(manifest) == 1


def test_postprocess_stages_emit_events(tmp_path):
    events = StageEventBuffer()
    tf = run_table_figure_stage(mono_pdf=None, dual_pdf=None, events=events)
    assert tf.state == "skipped"
    layout = run_layout_stage(mono_pdf=None, events=events, profile="letter")
    assert layout.state == "completed"
    assert events.last_for("layout").state == "completed"
