from __future__ import annotations

import pytest

from qyunslation.pipeline.executors.legacy import OfficeExecutor


@pytest.mark.asyncio
async def test_office_executor_requires_ad_prompt_for_ad_domain(monkeypatch):
    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **_kwargs):
            raise AssertionError("should not launch without AD prompt")

    monkeypatch.setattr(
        "qyunslation.server.get_translation_service",
        lambda: FakeService(),
    )
    executor = OfficeExecutor()
    with pytest.raises(RuntimeError, match="AD prompt missing"):
        await executor.start(
            content=b"doc",
            filename="ad.docx",
            declared_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            target_language="简体中文",
            settings={"domain_profile": "ad"},
        )


@pytest.mark.asyncio
async def test_office_executor_passes_ad_prompt(monkeypatch):
    captured = {}

    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **kwargs):
            captured.update(kwargs)
            return {"task_id": "office-1"}

    monkeypatch.setattr(
        "qyunslation.server.get_translation_service",
        lambda: FakeService(),
    )
    # 生产 office.env 的 OFFICE_LOCK 会在校验期用环境 CUSTOM_PROMPT 覆盖字段，
    # sidecar 随后再按 domain_profile 重新编译 AD 提示词；本测试只断言执行器侧透传。
    monkeypatch.delenv("DOCUTRANSLATE_OFFICE_LOCK", raising=False)
    executor = OfficeExecutor()
    launch = await executor.start(
        content=b"doc",
        filename="ad.docx",
        declared_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        target_language="简体中文",
        settings={
            "domain_profile": "ad",
            "profile": "医学研究文献",
            "ad_prompt_text": "AD compiled prompt",
        },
    )
    assert launch.task_id == "office-1"
    payload = captured["payload"]
    assert payload.domain_profile == "ad"
    assert payload.custom_prompt == "AD compiled prompt"
