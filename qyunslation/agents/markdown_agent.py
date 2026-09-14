# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
import re
from dataclasses import dataclass

from .agent import Agent, AgentConfig
from ..glossary.glossary import Glossary
from ..structure.references import (
    ReferenceProtectionError,
    mask_reference_sections,
    restore_reference_sections,
)


def get_original_markdown(prompt: str):
    match = re.search(r'<input>\n(.*)\n</input>', prompt, re.DOTALL)
    if match:
        return match.group(1)
    else:
        raise ValueError("无法从prompt中提取初始文本")


def generate_prompt(markdown_text: str, to_lang: str):
    return f"""
Treat the text input as markdown text and translate it into {to_lang},output translation ONLY.
- NO explanations. NO notes.
- For special tags or other non-translatable elements (like codes, brand names, specific jargon), keep them in their original form.
- All formulas, regardless of length, must be represented as valid, parsable LaTeX. They must be correctly enclosed by `$`, `\\(\\)`, or `$$`. If a formula is not formatted correctly, you must fix it.
- Remove or correct any obviously abnormal characters, but without altering the original meaning.
- When citing references, strictly preserve the original text; do not translate them. Examples of reference formats are as follows:
  [1] Author A, Author B. "Original Title". Journal, 2023.
  [2] 作者C. 《中文标题》. 期刊, 2022.
- Output the translated markdown text as plain text (not in a markdown code block, with no extraneous text).

The markdown text input:
<input>
 {markdown_text}
</input>
"""


@dataclass
class MDTranslateAgentConfig(AgentConfig):
    to_lang: str
    custom_prompt: str | None = None
    glossary_dict: dict[str, str] | None = None


class MDTranslateAgent(Agent):
    def __init__(self, config: MDTranslateAgentConfig):
        super().__init__(config)
        self.to_lang = config.to_lang
        self.system_prompt = f"""
# Role
You are a professional machine translation engine.
"""
        self.custom_prompt = config.custom_prompt
        if config.custom_prompt:
            self.system_prompt += "\n# **Important rules or background** \n" + self.custom_prompt + '\nEND\n'
        self.glossary_dict = config.glossary_dict

    def _pre_send_handler(self, system_prompt, prompt):
        if self.glossary_dict:
            glossary = Glossary(glossary_dict=self.glossary_dict)
            system_prompt += glossary.append_system_prompt(prompt)
        return system_prompt, prompt

    def send_chunks(self, prompts: list[str]):
        source_prompts = list(prompts)
        masked_prompts: list[dict[str, str]] = []
        requests: list[str] = []
        for source in source_prompts:
            masked, sections = mask_reference_sections(source)
            masked_prompts.append(sections)
            requests.append(generate_prompt(masked, self.to_lang))
        translated = super().send_prompts(
            prompts=requests,
            pre_send_handler=self._pre_send_handler,
            error_result_handler=lambda prompt, logger: get_original_markdown(prompt),
        )
        return self._restore_results(source_prompts, masked_prompts, translated)

    async def send_chunks_async(self, prompts: list[str]):
        source_prompts = list(prompts)
        masked_prompts: list[dict[str, str]] = []
        requests: list[str] = []
        for source in source_prompts:
            masked, sections = mask_reference_sections(source)
            masked_prompts.append(sections)
            requests.append(generate_prompt(masked, self.to_lang))
        translated = await super().send_prompts_async(
            prompts=requests,
            pre_send_handler=self._pre_send_handler,
            error_result_handler=lambda prompt, logger: get_original_markdown(prompt),
        )
        return self._restore_results(source_prompts, masked_prompts, translated)

    def _restore_results(
        self,
        sources: list[str],
        sections: list[dict[str, str]],
        translated: list[str],
    ) -> list[str]:
        restored: list[str] = []
        for source, protected, result in zip(sources, sections, translated):
            try:
                restored.append(restore_reference_sections(result, protected, strict=True))
            except ReferenceProtectionError:
                # Never return a citation that the model was allowed to alter.
                # Returning the source chunk is conservative and observable in
                # logs through the existing agent error channel.
                self.logger.warning("reference sentinel lost; returning source chunk")
                restored.append(source)
        return restored

    def update_glossary_dict(self, update_dict: dict | None):
        # PLAN-034d0：经 Glossary.update 规范化，禁止裸 | 合并
        from qyunslation.glossary.glossary import Glossary

        gloss = Glossary(self.glossary_dict or {})
        gloss.update(update_dict or {})
        self.glossary_dict = gloss.glossary_dict
