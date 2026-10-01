# SPDX-License-Identifier: MPL-2.0
import json
import runpy
from pathlib import Path

from qyunslation.structure.translation_trace import (
    OVERRIDES_FILE,
    TRACE_FILE,
    postprocess_translation,
)


def test_postprocess_applies_exact_affiliation_override_sanitizes_and_traces(tmp_path: Path):
    source = "1 Department of Dermatology, New York Medical College"
    (tmp_path / OVERRIDES_FILE).write_text(
        json.dumps({source: "纽约医学院皮肤科\u0003"}, ensure_ascii=False), encoding="utf-8"
    )

    result = postprocess_translation(source, "错误译名<style id='3'>", workdir=tmp_path)

    assert result == "纽约医学院皮肤科 "
    trace = json.loads((tmp_path / TRACE_FILE).read_text(encoding="utf-8").splitlines()[0])
    assert trace["source_text"] == source
    assert trace["machine_text"] == result


def test_babeldoc_patcher_passes_source_and_translation_to_plan074_hook():
    script = runpy.run_path("scripts/apply-pdf2zh-045c-sanitize.py")
    raw = """logger = logging.getLogger(__name__)

    def post_translate_paragraph(
        self,
        paragraph: PdfParagraph,
        tracker: ParagraphTranslateTracker,
        translate_input,
        translated_text: str,
    ):
        \"\"\"Post-translation processing: update paragraph with translated text.\"\"\"
        tracker.set_output(translated_text)
"""
    patched, changed = script["patch"](raw)

    assert changed is True
    assert "_QY_074_POSTPROCESS(paragraph.unicode, translated_text)" in patched
