# SPDX-License-Identifier: MPL-2.0
from qyunslation.pipeline.progress import (
    cli_progress_is_text_only,
    progress_for_units,
    stage_unit_denominator,
)


def test_progress_with_denominator():
    assert progress_for_units(units_done=5, units_total=10) == 50.0


def test_progress_without_denominator_is_null():
    assert progress_for_units(units_done=3, units_total=None) is None
    assert progress_for_units(units_done=3, units_total=0) is None


def test_stage_denominators():
    counts = {"pages": 8, "text_objects": 40, "table_figure_objects": 3, "qa_checks": 6}
    assert stage_unit_denominator("ocr", counts=counts) == 8
    assert stage_unit_denominator("text", counts=counts) == 40
    assert stage_unit_denominator("export", counts=counts) is None


def test_cli_progress_not_export():
    assert cli_progress_is_text_only("Progress: 1.0 translating") is True
    assert cli_progress_is_text_only("Progress: 1.0, export") is False
