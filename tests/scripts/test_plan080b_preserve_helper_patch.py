# SPDX-License-Identifier: MPL-2.0
"""PLAN-080：保留谓词 helper 的补丁——旧版静默失败，新版第一次失败时记一条告警。"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("apply_033h", ROOT / "scripts" / "apply-pdf2zh-fidelity-033h.py")
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

ENGINE_STUB = (
    "import logging\n"
    "logger = logging.getLogger(__name__)\n"
    "{helper}\n"
    "class ILTranslatorLLMOnly:\n"
    "    def translate(self, docs: Document) -> None:\n"
    "        pass\n"
)


def _load(source: str):
    namespace: dict = {"__name__": "il_translator_llm_only_stub", "Document": object}
    exec(compile(source, "stub.py", "exec"), namespace)  # noqa: S102
    return namespace


def test_old_helper_is_upgraded_in_place_and_the_upgrade_is_idempotent():
    old = ENGINE_STUB.format(helper=patch.OLD_HELPER)
    new, changed = patch.patch_il(old)
    assert changed
    assert "_qy_033h_warn_once" in new
    assert patch.OLD_HELPER.strip() not in new
    again, changed_again = patch.patch_il(new)
    assert not changed_again or again == new
    assert again.count("def _QY_033H_PRESERVE") == 1


def test_fresh_file_gets_the_new_helper():
    new, changed = patch.patch_il(ENGINE_STUB.format(helper=""))
    assert changed and "_qy_033h_warn_once" in new


def test_upgraded_helper_warns_once_and_still_returns_false(monkeypatch, caplog):
    source, _ = patch.patch_il(ENGINE_STUB.format(helper=patch.OLD_HELPER))
    namespace = _load(source)
    monkeypatch.setitem(sys.modules, "qyunslation.structure.babeldoc_policy", None)  # 导入失败
    with caplog.at_level(logging.WARNING):
        assert namespace["_QY_033H_PRESERVE"]("2. Some paragraph") is False
        assert namespace["_QY_033H_PRESERVE"]("Another paragraph") is False
    messages = [r.getMessage() for r in caplog.records if "preserve policy unavailable" in r.getMessage()]
    assert len(messages) == 1  # 只记一次，不刷屏


def test_upgraded_helper_delegates_when_the_policy_is_importable():
    source, _ = patch.patch_il(ENGINE_STUB.format(helper=patch.OLD_HELPER))
    namespace = _load(source)
    assert namespace["_QY_033H_PRESERVE"]("Medical Director") is True
    assert namespace["_QY_033H_PRESERVE"]("Clinical Pharmacology") is False
