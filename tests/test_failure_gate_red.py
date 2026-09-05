from qyunslation.agents.agent import AgentResultError
from qyunslation.agents.segments_agent import (
    SegmentsTranslateAgent,
    SegmentsTranslateAgentConfig,
    generate_prompt,
)
from qyunslation.server.core import (
    _get_unresolved_error_count,
    _translation_failure_message,
)


def test_failed_translation_does_not_return_source_as_success():
    agent = SegmentsTranslateAgent(
        SegmentsTranslateAgentConfig(
            base_url="http://example.invalid/v1",
            api_key="x",
            model_id="m",
            to_lang="中文",
        )
    )
    origin_prompt = generate_prompt('{"1":"Hello world."}', "中文")

    try:
        agent._error_result_handler(origin_prompt, agent.logger)
    except Exception as exc:
        assert isinstance(exc, AgentResultError)
        return

    raise AssertionError("all-request failure must raise, not return source text")


def test_unresolved_errors_block_success():
    stats = {"total": {"request_count": 4, "unresolved_errors": 4}}
    assert _get_unresolved_error_count(stats) == 4
    assert _translation_failure_message(stats) == (
        "翻译请求失败：有 4 个分块未生成有效译文，已阻止导出原文/伪译文。"
    )


def test_clean_stats_do_not_block_success():
    stats = {"total": {"request_count": 2, "unresolved_errors": 0}}
    assert _get_unresolved_error_count(stats) == 0
    assert _translation_failure_message(stats) is None
