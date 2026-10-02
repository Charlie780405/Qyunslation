"""PLAN-076b/c: versioned AD prompt registry and deterministic compiler.

The compiler deliberately returns a metadata-only snapshot for APIs.  The
compiled prompt is used by translation adapters, while the digest is the
stable audit key stored with a run.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

AD_DOMAIN_PROFILE = "ad"
PROMPT_VERSION = "076-v1"
SUPPORTED_DIRECTIONS = {"en-zh", "zh-en"}
SUPPORTED_AD_DOCUMENTS = {"医学研究文献", "临床研究文档"}

_DOMAIN_ANCHORS = (
    r"\batopic dermatitis\b",
    r"\beczema\b",
    r"\bdupilumab\b",
    r"\btralokinumab\b",
    r"\bSCORAD\b",
    r"\bEASI(?:-75)?\b",
    r"特应性皮炎|湿疹|度普利尤单抗|曲罗芦单抗|皮炎面积严重度指数",
)

_BASE = """你是受控的医学翻译引擎。只输出目标语言译文，不解释、不补写原文没有的事实。
严格保持段落、表格、占位符、引用、数字、单位、统计量、否定和情态的对应关系。
对不确定内容保持原文并标记为需人工审核，禁止猜测药物、靶点、终点或剂量。
"""

_AD_DOMAIN = """领域：特应性皮炎（AD）医学研究。熟悉皮肤科临床研究、疗效量表、免疫通路和生物制剂。
术语优先使用任务术语策略中的批准译名；药物通用名、靶点、受体、量表和试验代号不得擅自改写。
不要把药物、靶点、剂量、统计量或终点改写成事实。
"""

_DIRECTION = {
    "en-zh": "语言方向：English → 简体中文。中文须符合中国医学论文和临床研究文档习惯。",
    "zh-en": "语言方向：简体中文 → English。英文须符合国际医学论文和临床研究写作习惯。",
}

_DOCUMENT = {
    "医学研究文献": "文档类型：医学研究文献。保持 IMRaD 结构、参考文献、图表题注和统计表述的学术准确性。",
    "临床研究文档": "文档类型：临床研究文档。保持访视、终点、入排标准、安全性和方案约束的可执行含义。",
}

_TASK = {
    "translate": "任务：翻译。逐段完成等义转换；不合并或拆分可追踪分段，不删除空分段。",
}


@dataclass(frozen=True)
class PromptContext:
    domain_profile: str = "general"
    direction: str = "en-zh"
    document_profile: str = "通用医药文档"
    task: str = "translate"


@dataclass(frozen=True)
class CompiledPrompt:
    profile_id: str
    version: str
    digest: str
    domain_profile: str
    direction: str
    document_profile: str
    task: str
    text: str

    def snapshot(self) -> dict[str, str]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "digest": self.digest,
            "domain_profile": self.domain_profile,
            "direction": self.direction,
            "document_profile": self.document_profile,
            "task": self.task,
            "compiler_version": "076-compiler-v1",
            "qa_rule_version": "076-qa-v1",
        }


def _slug_document(profile: str) -> str:
    return {"医学研究文献": "literature", "临床研究文档": "clinical"}.get(profile, "general")


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def compile_prompt(context: PromptContext) -> CompiledPrompt:
    domain = (context.domain_profile or "general").strip().casefold()
    direction = (context.direction or "").strip().casefold()
    document = (context.document_profile or "通用医药文档").strip()
    task = (context.task or "translate").strip()
    if direction not in SUPPORTED_DIRECTIONS:
        raise ValueError(f"unsupported {'AD ' if domain == AD_DOMAIN_PROFILE else ''}direction")
    if task not in _TASK:
        raise ValueError("unsupported prompt task")
    if domain == AD_DOMAIN_PROFILE:
        if document not in SUPPORTED_AD_DOCUMENTS:
            raise ValueError("unsupported AD document profile")
        text = "\n".join((_BASE, _AD_DOMAIN, _DIRECTION[direction], _DOCUMENT[document], _TASK[task])).strip()
        profile_id = f"ad.{direction}.{_slug_document(document)}.{task}.v1"
    elif domain == "general":
        text = "\n".join((_BASE, _DIRECTION[direction], _TASK[task])).strip()
        profile_id = f"general.{direction}.general.{task}.v1"
    else:
        raise ValueError("unsupported domain profile")
    return CompiledPrompt(
        profile_id=profile_id,
        version=PROMPT_VERSION,
        digest=_digest(text),
        domain_profile=domain,
        direction=direction,
        document_profile=document,
        task=task,
        text=text,
    )


def detect_domain_evidence(text: str) -> bool:
    value = text or ""
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _DOMAIN_ANCHORS)
