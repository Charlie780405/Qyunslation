import json
import logging

import pytest

from qyunslation.agents.agent import PartialAgentResultError
from qyunslation.agents.segments_agent import (
    SegmentsTranslateAgent,
    SegmentsTranslateAgentConfig,
    generate_prompt,
)


def _agent():
    return SegmentsTranslateAgent(
        SegmentsTranslateAgentConfig(
            base_url="http://example.invalid/v1",
            api_key="x",
            model_id="m",
            to_lang="中文",
            retry=1,
        )
    )


def test_missing_segment_ids_are_not_returned_as_source_fallback():
    agent = _agent()
    prompt = generate_prompt(json.dumps({"0": "first", "1": "second"}, ensure_ascii=False), "中文")

    with pytest.raises(PartialAgentResultError) as exc_info:
        agent._result_handler(
            '[{"id":"0","t":"第一"}]',
            prompt,
            logging.getLogger("test-partial-result"),
        )

    assert exc_info.value.partial_result == {"0": "第一"}
    assert "1" not in exc_info.value.partial_result


def test_assemble_translated_segments_rejects_missing_ids():
    agent = _agent()
    with pytest.raises(Exception) as exc_info:
        agent._assemble_translated_segments(
            {"0": "first", "1": "second"}, [(0, 2)], [{"0": "第一"}]
        )
    assert "缺失" in str(exc_info.value)


def test_all_source_text_in_output_is_rejected_by_result_handler():
    agent = _agent()
    prompt = generate_prompt(json.dumps({"0": "first", "1": "second"}, ensure_ascii=False), "中文")

    with pytest.raises(Exception) as exc_info:
        agent._result_handler(
            '[{"id":"0","t":"first"},{"id":"1","t":"second"}]',
            prompt,
            logging.getLogger("test-source-output"),
        )

    assert "翻译失败" in str(exc_info.value) or "原文" in str(exc_info.value)
