from __future__ import annotations

from qyunslation.core.factory import create_workflow_from_payload
from qyunslation.core.schemas import MarkdownWorkflowParams


def test_direct_factory_path_uses_the_same_ad_prompt_compiler():
    payload = MarkdownWorkflowParams(
        workflow_type="markdown_based",
        skip_translate=True,
        domain_profile="ad",
        document_profile="医学研究文献",
        to_lang="简体中文",
        convert_engine="identity",
    )
    workflow = create_workflow_from_payload(payload)
    prompt = workflow.config.translator_config.custom_prompt
    assert prompt is not None
    assert "特应性皮炎" in prompt
    assert "不要把药物、靶点、剂量、统计量或终点改写成事实" in prompt
