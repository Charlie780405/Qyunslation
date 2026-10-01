# SPDX-License-Identifier: MPL-2.0
"""PLAN-071g Task 4：任务模型/外发/指纹快照（创建时一次性写入，只读）。"""
from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from qyunslation.pipeline.model_profiles import PROFILES

PROMPT_VERSION = "071-prompt-v1"
_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def patch_fingerprint() -> str | None:
    """pdf2zh/BabelDOC 补丁指纹（071a 脚本）；脚本或安装路径不可用时为 None。"""
    path = _ROOT / "scripts" / "plan071_patch_fingerprint.py"
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_p071_patch_fp", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("_p071_patch_fp", module)
        spec.loader.exec_module(module)
        report = module.build_report(module.resolve_site(None))
        return str(report.get("fingerprint_sha256") or "") or None
    except Exception:
        return None


def egress_scope(*, classification: str, translator_id: str | None, term_id: str | None) -> str:
    translator = PROFILES.get(translator_id or "")
    if translator is not None and translator.provider not in {"ollama", "internal"}:
        return "full_document"
    if term_id and (PROFILES.get(term_id) is not None):
        return "redacted_term_snippets"
    return "none"


def build_run_model_snapshot(
    *,
    classification: str,
    translator_id: str | None,
    term_id: str | None,
    termbase_version: str | None,
    pipeline: str,
) -> dict[str, Any]:
    translator = PROFILES.get(translator_id or "internal-qwen-quality")
    term = PROFILES.get(term_id or "")
    return {
        "pipeline": pipeline,
        "model_snapshot": {
            "profile_id": translator.profile_id if translator else translator_id,
            "provider": translator.provider if translator else None,
            "model_id": translator.model_id if translator else None,
            # 别名不静默升级：版本在探测落库前显式标记为未探测，不冒充真实上报版本。
            "reported_version": None,
            "version_pinned": False,
            "experimental": bool(translator and translator.experimental),
            "term_profile_id": term.profile_id if term else None,
            "term_model_id": term.model_id if term else None,
            "prompt_version": PROMPT_VERSION,
            "termbase_version": termbase_version,
            "document_classification": classification,
            "egress_scope": egress_scope(
                classification=classification, translator_id=translator_id, term_id=term_id
            ),
            "patch_fingerprint": patch_fingerprint(),
        },
    }
