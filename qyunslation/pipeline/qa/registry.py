# SPDX-License-Identifier: MPL-2.0
"""PLAN-078b：QA 规则注册表（中文文案、处置类别、定位能力、指纹与规则集版本）。

Every QA finding code the pipeline can emit is declared here once. The registry answers:
what does this mean for the reader (title / why / how), what may be done about it (class and
disposition rules), whether it can point at a place in the document, and what makes two
findings "the same problem" across re-checks (fingerprint).

Classes (see PLAN-078 §5.2):

* ``C1`` critical fact (numbers, units, negation, missing text): can only be
  fixed, or confirmed as a rule false positive by someone with a confirmer role (term_admin, admin, owner; the
  reporter may confirm their own report, which the audit trail marks). Never waivable.
* ``C2`` layout / metadata: fix, or a reviewer waives it with a reason.
* ``C3`` the checker could not run (or its integrity failed): says nothing about the
  translation; re-run the check. No dispositions.
* ``C4`` terminology: fix, or a reviewer waives it with a reason.
* ``W`` warning: acknowledge (does not block delivery).
* ``I`` information.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

C1, C2, C3, C4, WARN, INFO = "C1", "C2", "C3", "C4", "W", "I"


@dataclass(frozen=True)
class RuleInfo:
    code: str
    rule_class: str
    title: str
    why: str
    how: str
    # "page" = anchors name a document page; "excerpt" = anchors quote the text; "none" = whole-document rule
    locatable: str = "none"
    unlocatable_reason: str = "该规则按全文统计，不对应单一位置"
    batchable: bool = False
    # Fields that make two findings the same problem across re-checks (empty = code + place only).
    identity_keys: tuple[str, ...] = ()


def _r(code: str, rule_class: str, title: str, why: str, how: str, **kw: Any) -> tuple[str, RuleInfo]:
    return code, RuleInfo(code=code, rule_class=rule_class, title=title, why=why, how=how, **kw)


_RULES: dict[str, RuleInfo] = dict(
    [
        # ---- C1: critical facts -------------------------------------------------------------
        _r("AD_NUMBER_DRIFT", C1, "数字、剂量或统计量与原文不一致",
           "剂量、百分比、样本量等数值改变会直接改变临床含义，不能带着这类差异交付。",
           "对照下方“原文位置”核对译文中是否漏译或改写了这些数值，修正后重新翻译；若确认是规则把格式差异误判为缺失，请反馈误报，由另一位术语管理员或管理员确认。",
           locatable="excerpt", identity_keys=("missing_in_target", "unexpected_in_target")),
        _r("AD_NEGATION_DRIFT", C1, "否定含义在译文中丢失",
           "“没有/不”之类的否定被漏掉会把原文意思译反。",
           "核对原文中含否定的句子在译文里是否仍表达否定，修正后重新检查。",
           locatable="excerpt"),
        _r("AD_MODALITY_DRIFT", C1, "义务、许可或禁止的语气发生变化",
           "“必须/禁止/可以”的差异会改变方案或说明书的约束力。",
           "核对原文中的 must / shall / prohibited 等表述在译文里是否保持同等强度，修正后重新检查。"),
        _r("AD_REPAIR_FACT_DRIFT", C1, "自动修复改变了受保护的事实",
           "语义修复步骤改动了数字、剂量等受保护内容，修复结果不可信。",
           "不要采用自动修复结果，请重新翻译；如反复出现请联系管理员。"),
        _r("UNTRANSLATED_BODY", C1, "译文大部分仍是外文，疑似未翻译",
           "整段未翻译的内容无法交付。",
           "查看下方页面，确认是否真的漏译（扫描件、图片文字或表格最常见），必要时开启 OCR 后重新翻译。",
           locatable="page", identity_keys=("output_kind",)),
        _r("EMPTY_TRANSLATION", C1, "译文为空",
           "没有译文，无法交付。", "检查翻译引擎和模型是否可用，然后重新翻译。"),
        _r("LITERAL_MISSING_EMAIL", C1, "原文中的邮箱地址在译文中缺失或被改写",
           "联系方式被改动可能导致无法联系到责任方。",
           "对照原文位置，把邮箱原样保留在译文中，然后重新检查。",
           locatable="excerpt", identity_keys=("kind", "missing")),
        _r("LITERAL_MISSING_IND", C1, "原文中的 IND / NCT 编号在译文中缺失或被改写",
           "试验或申报编号错误会让监管文件无法对应。",
           "对照原文位置，把编号原样保留在译文中，然后重新检查。",
           locatable="excerpt", identity_keys=("kind", "missing")),
        # PLAN-079: a garbled-text hit is often an invisible control character in the PDF text layer, which a
        # reviewer settles by looking at the page. So it is C2 (a reviewer waives it with a written reason,
        # one person, audited) rather than C1 (second-person confirmation), unlike numbers or negation.
        _r("TEXT_ENCODING_ARTIFACT", C2, "译文含乱码或不可打印字符",
           "乱码意味着文字在转换中损坏；但命中也可能只是 PDF 文本层里看不见的控制字符。",
           "查看下方页面中的乱码位置；展开“技术细节”可看到是哪一类字符（替换符、控制字符或编码错乱）及其码点。"
           "如果页面上确实读不出乱码，复核人写明理由后可授权例外；确有乱码则重新翻译（必要时换用文本型 PDF 或原始 Word 文档）。",
           locatable="page", identity_keys=("output_kind",)),
        _r("TEXT_LAYER_SPACE_MAP", WARN, "译文文本层空格被映射为控制字符",
           "页面通常仍可读；复制或搜索时会出现异常符号。常见于部分 PDF 字体把空格字形的 ToUnicode 写成了控制字符。",
           "对照页面确认正文可读即可确认已阅；若复制结果也要干净，可重新导出或开启空格 CMap 修复后再交付。",
           locatable="page", identity_keys=("detectors",)),
        _r("TEXT_ENCODING_INHERITED", WARN, "译文中的异常字符在源文同一页也存在",
           "同一页的源文已经带有这些字符，多半来自源文 PDF 的字体或编码，不是翻译造成的。",
           "对照源文同一页确认；确属源文原样的可确认已阅。",
           locatable="page", identity_keys=("detectors",)),
        _r("IL_MARKUP_LEAK", C1, "译文中残留内部排版标记",
           "内部标记泄漏到正文会让文档无法阅读。",
           "请重新翻译；如反复出现请联系管理员。",
           locatable="page", identity_keys=("output_kind",)),
        # ---- C2: layout / metadata ------------------------------------------------------------
        _r("LOGO_MISSING", C2, "原文首页图片（疑似标识或印章）未在译文中保留",
           "机构标识或印章缺失可能让文件失去效力。",
           "查看译文首页是否确有标识缺失；若只是图片被重新编码，由复核人说明理由后授权例外。",
           locatable="page", identity_keys=("output_kind",)),
        _r("PAGE_COUNT_MISMATCH", C2, "译文页数与原文不一致",
           "页数变化通常意味着内容溢出、缺页或版式损坏。",
           "对照原文和译文检查是否有缺页或内容溢出；确属排版差异时由复核人说明理由后授权例外。",
           unlocatable_reason="页数差异不属于某一页", identity_keys=("output_kind",)),
        _r("TABLE_TEXT_OVERLAP", C2, "译文表格区域文字框严重重叠",
           "表头或数值叠在一起通常表示列对齐失败，读者无法核对数据。",
           "在对照视图查看对应页；确认表格不可读后重新翻译或开启表格后处理；若仅为脚注叠字可由复核人说明理由后授权例外。",
           locatable="page", identity_keys=("output_kind",)),
        _r("AUTHOR_METADATA_CHANGED", C2, "作者信息与原文不完全一致",
           "作者信息要求与原文逐行一致。",
           "对照原文位置，把作者行改回与原文一致；若只是换行或标点造成的差异，由复核人说明理由后授权例外。",
           locatable="page", identity_keys=("missing",)),
        _r("ORDINAL_ARTIFACT", C2, "出现序数上标伪影（如 ^{th}）",
           "排版残留会出现在正文中。", "重新翻译，必要时手工修正对应文字。"),
        _r("MANIFEST_EMPTY_OBJECTS", C2, "文档结构中没有可处理的对象",
           "没有识别到任何文字或表格对象，译文不可信。", "确认文件是否为空白或纯图片，必要时开启 OCR 后重新预检。"),
        _r("GENERATION_MISMATCH", C2, "结构清单与任务版本不一致",
           "说明检查对象可能来自旧版本。", "请重新检查；如仍出现请联系管理员。"),
        _r("AD_DOMAIN_EVIDENCE_MISSING", C2, "原文缺少可验证的专业领域依据",
           "无法证明该文档属于所选专业领域，专业规则可能不适用。",
           "确认文档领域选择是否正确；确属该领域但缺少锚点时由复核人说明理由后授权例外。"),
        # ---- C3: the checker could not run -----------------------------------------------------
        _r("TERM_EXTRACTION_DEGRADED", C3, "术语抽取服务未能完成检查",
           "检查服务当时无法运行，这不代表译文有问题，但也不能当作检查通过。",
           "等术语模型服务恢复后点击“重新检查”。"),
        _r("AD_QA_SOURCE_UNAVAILABLE", C3, "缺少可供检查的译文文件",
           "没有译文文件，质量检查无法进行。", "确认翻译是否真正完成，必要时重新翻译。"),
        _r("QA_INPUT_UNAVAILABLE", C3, "无法读取原文或译文 PDF",
           "文本和版式检查没有执行，不能当作检查通过。", "确认文件未损坏后点击“重新检查”。"),
        _r("QA_ROUND_FAILED", C3, "质量检查执行失败（系统错误）",
           "检查过程本身出错，不代表译文有问题。", "点击“重新检查”；反复出现请联系管理员。"),
        _r("TERM_SNAPSHOT_INCONSISTENT", C3, "术语快照校验失败",
           "无法证明本次检查使用的术语与检查器一致。", "点击“重新检查”；仍失败请联系管理员。"),
        _r("AD_QA_DEGRADED", C3, "语义检查不可用或超时",
           "确定性检查已通过，但语义检查没有完成，暂不可批准。", "服务恢复后点击“重新检查”。"),
        # ---- C4: terminology --------------------------------------------------------------------
        _r("TERM_HIGH_RISK_CONFLICT", C4, "高风险术语未使用批准译名",
           "药名、适应症等高风险术语必须与术语库一致。",
           "对照下方证据把译名改成批准译法后重新翻译；若上下文确实不适用，由复核人说明理由后授权例外。",
           identity_keys=("concept_id", "expected")),
        _r("TERM_FORBIDDEN_TARGET", C4, "出现被禁用的术语译法",
           "该译法已被术语库明确禁止。", "改用批准译法后重新翻译。", identity_keys=("concept_id", "forbidden")),
        _r("TERM_TARGET_MISSING", C4, "批准的术语译名未出现在译文中",
           "术语不一致会影响全文统一性。", "核对译文是否使用了其他译法；确属同义表达时可授权例外。",
           identity_keys=("concept_id", "expected"), batchable=True),
        _r("TERM_REVIEW_REQUIRED", C4, "高风险术语在本文译法不统一，需要复核",
           "同一个药名、靶点、终点等在同一份文件里有多种译法，或术语库对它给出了不同的批准译名，会影响全文统一性和含义。",
           "对照下方证据把译法统一为一种后重新翻译；若上下文确实需要不同译法，由复核人写明理由后授权例外。此处理只作用于本文，不会写入共享词库。",
           locatable="excerpt", identity_keys=("source_norm", "signal")),
        _r("AD_TERM_MISSING", C4, "批准术语未按策略出现",
           "专业术语应按术语库使用批准译法。", "核对译文用词，必要时重新翻译；同义表达可授权例外。",
           identity_keys=("source_term", "expected_target")),
        # ---- warnings ---------------------------------------------------------------------------
        _r("LATIN_RESIDUE", WARN, "译文中英文残留较多",
           "可能有未翻译的段落，也可能只是药名、缩写或参考文献。",
           "查看下方页面确认；属于正常保留的内容可确认已阅。", locatable="page", identity_keys=("output_kind",),
           batchable=True),
        # PLAN-080f: paragraph-level and typography checks on the output PDF; warnings only until their
        # false-positive rate is known (D4), so not batchable.
        _r("UNTRANSLATED_PARAGRAPH", WARN, "译文中有整段仍是外文",
           "这些段落与源文同页逐字相同，又不是人名、职务、机构、网址或参考文献，很可能是漏译；全文英文占比低时 \"英文残留\" 检查看不到它们。",
           "查看下方页面确认；确属不需要翻译的内容可确认已阅，否则重新翻译。",
           locatable="page", identity_keys=("output_kind",)),
        _r("REFERENCE_ENTRIES_CHANGED", WARN, "参考文献在译文中与源文不一致",
           "参考文献条目应当原样保留；被翻译或改写会让引用无法对应。",
           "查看下方页面确认；确属不需要保留的内容可确认已阅，否则重新翻译。",
           locatable="page", identity_keys=("output_kind",)),
        _r("FONT_FAMILY_SPRAWL", WARN, "译文页面的字体种类明显多于源文",
           "同一页混用多种字体会让译文看起来不统一。",
           "查看下方页面；如需统一，开启“统一译文字体”后重新生成。", locatable="page",
           identity_keys=("output_kind",), batchable=True),
        _r("DECORATION_DANGLING", WARN, "下划线等装饰线没有跟上译文",
           "译文重排后，原来画在英文下面的线可能过长、悬空或压在别的文字下。",
           "查看下方页面；如需修正，开启“装饰线随文”后重新生成。", locatable="page",
           identity_keys=("output_kind",), batchable=True),
        _r("FALLBACK_PRESENT", WARN, "存在回退翻译的段落", "回退段落的质量没有经过完整流程。",
           "人工复核这些段落。", batchable=True),
        _r("LITERAL_MISSING_URL", WARN, "原文中的网址在译文中缺失或被改写", "网址被改写可能导致链接失效。",
           "对照原文位置核对网址。", locatable="excerpt", identity_keys=("kind", "missing"), batchable=True),
        # D2: kept as warnings, and deliberately NOT batchable until their false-positive rate is known.
        _r("LITERAL_MISSING_DOSE", WARN, "原文中的剂量在译文中缺失或被改写",
           "剂量错误后果严重；本检查目前只作警告，须逐项确认。",
           "对照原文位置逐项核对剂量。", locatable="excerpt", identity_keys=("kind", "missing")),
        _r("LITERAL_MISSING_FREQ", WARN, "原文中的给药频次在译文中缺失或被改写",
           "频次错误会改变用药方案；本检查目前只作警告，须逐项确认。",
           "对照原文位置逐项核对频次。", locatable="excerpt", identity_keys=("kind", "missing")),
        _r("TERM_SNAPSHOT_PENDING", WARN, "术语快照尚未完成", "术语检查可能不完整。", "稍后重新检查。", batchable=True),
        _r("DRUG_NAME_DRIFT", WARN, "译文出现术语库之外的药名", "可能混入了其他药物的名称。", "核对药名。"),
        # ---- info -------------------------------------------------------------------------------
        _r("QA_INSPECTION_SUMMARY", INFO, "确定性 QA 取证摘要", "记录本轮检查的输入范围。", "无需处理。"),
    ]
)


def rule_for(code: str) -> RuleInfo:
    """Registered rule, or a conservative C1 placeholder for a code nobody declared."""
    info = _RULES.get(code)
    if info is not None:
        return info
    logger.warning("unregistered QA code %s; treating it as a critical-fact rule", code)
    return RuleInfo(
        code=code,
        rule_class=C1,
        title=f"未登记检查项（{code}）",
        why="该检查项尚未登记处理说明，按关键事实处理，不能放行。",
        how="请联系管理员登记该检查项。",
    )


def is_registered(code: str) -> bool:
    return code in _RULES


# ------------------------------------------------------------------------------------------------
# remedies: what a person can actually DO about a finding, as clickable options (PLAN-079)
# ------------------------------------------------------------------------------------------------

# Prefilled, editable reasons for the "go ahead anyway" choices. They say what to check, so the
# reviewer confirms a fact instead of inventing a sentence (a reason must be at least 10 characters).
_WAIVER_REASONS: dict[str, str] = {
    "TEXT_ENCODING_ARTIFACT": "已查看对应页面，页面上读不出乱码，内容可以接受（命中的多半是文本层里不可见的控制字符）。",
    "TEXT_LAYER_SPACE_MAP": "已查看对应页面，正文可读；命中的是文本层空格字形映射，不影响阅读。",
    "TABLE_TEXT_OVERLAP": "已对照原文表格，重叠不影响关键数据核对，或仅为脚注/装饰叠字。",
    "LOGO_MISSING": "已核对首页，标识或印章在译文中以其他形式保留，或本文不需要保留，不影响使用。",
    "PAGE_COUNT_MISMATCH": "已核对，译文页数与原文不同来自排版（行宽、字体或表格），内容完整。",
    "AUTHOR_METADATA_CHANGED": "已核对作者与单位信息，差异只是标点或格式，姓名与单位没有被改动。",
    "ORDINAL_ARTIFACT": "已核对，序数上标在译文中显示正常，不影响阅读。",
    "MANIFEST_EMPTY_OBJECTS": "已核对文档确实没有可处理的对象，译文内容完整，可以带着交付。",
    "GENERATION_MISMATCH": "已核对结构清单对应的就是当前版本，译文内容一致，可以带着交付。",
    "AD_DOMAIN_EVIDENCE_MISSING": "已核对原文的专业领域，译文按该领域处理是合适的，可以带着交付。",
}
_DEFAULT_WAIVER_REASON = "已逐项核对原文和译文，确认这一项不影响内容的正确性和使用，可以带着交付。"
_TERM_WAIVER_REASON = "本文上下文确需使用当前译法，已对照原文核对，不影响理解，保持现状。"
_FALSE_POSITIVE_REASON = "已对照原文核对，译文已正确保留该内容，检查规则误判。"
_ACKNOWLEDGE_REASON = "已查看该提示，属于正常保留或可接受的内容，不影响交付。"


def _remedy(rid: str, kind: str, label: str, why: str, **kw: Any) -> dict[str, Any]:
    return {"id": rid, "kind": kind, "label": label, "why": why, "action": "", "reason": "", "recommended": False, **kw}


def one_step_false_positive() -> dict[str, Any]:
    """Override for the C1 "false positive" remedy when the viewer may also confirm: report + confirm in one go."""
    return {
        "label": "核对过了，这是检查误报，放行",
        "why": "你有确认权限，所以反馈和确认一步完成；两条记录都会进入审计，并标注为自我确认（没有第二个人复核）。",
        "then": "confirm_false_positive",
    }


_CARRY_OVER_ACTIONS = {
    "grant_waiver": ("grant_waiver", "", "授权了例外"),
    "confirm_false_positive": ("report_false_positive", "confirm_false_positive", "确认为误报"),
    "acknowledge": ("acknowledge", "", "确认已阅"),
}


def carry_over_remedy(prior_action: str, prior_reason: str, prior_actor: str, can_confirm: bool) -> dict[str, Any] | None:
    """"Same conclusion as on the previous version", for a finding that came back identical after a regeneration.

    A disposition is never inherited silently (the new version's output is different), so it must be given
    again; this makes giving it again one click with the earlier reason already written in.
    """
    spec = _CARRY_OVER_ACTIONS.get(prior_action)
    if spec is None:
        return None
    action, then, verb = spec
    if prior_action == "confirm_false_positive" and not can_confirm:
        then = ""  # may report it again, but somebody with confirm rights has to finish it
    short = (prior_reason or "").strip().replace("\n", " ")
    return _remedy(
        "carry_over", "disposition", "沿用上一版的结论",
        f"上一版已由 {prior_actor} {verb}：{short[:60]}。这一版的输出重新生成过，需要再确认一次；"
        "同一个问题原样出现时，一键沿用，理由已预填，核对页面后提交即可。",
        action=action, reason=f"沿用上一版的结论：{short}"[:1000].ljust(10, "。"), recommended=True,
        **({"then": then} if then else {}),
    )


def pending_report_remedies(can_confirm: bool) -> list[dict[str, Any]]:
    """What to do while a false-positive report on a critical fact is waiting for confirmation."""
    locate = _remedy("locate", "locate", "先看问题所在的页面", "对照原文和译文，再决定确认还是驳回。")
    revise = _remedy(
        "revise", "revise", "重新生成修订版",
        "原版会保留。新版用同一套配置重新翻译并自动复检，这条问题可能随之消失。",
    )
    if can_confirm:
        return [
            locate,
            _remedy(
                "confirm", "disposition", "确认这是误报，放行",
                "已有人反馈这是误报。确认后阻断解除，记入审计。",
                action="confirm_false_positive", reason="已复核原文和译文，同意这是检查误报，放行。", recommended=True,
            ),
            _remedy(
                "reject", "disposition", "驳回：问题确实存在",
                "复核后认为问题是真的：阻断保留，需要修复或重新生成。",
                action="reject_false_positive", reason="复核后问题确实存在，驳回误报反馈，需要修复。",
            ),
            revise,
        ]
    revised = {**revise, "recommended": True}
    return [
        _remedy(
            "waiting", "info", "已反馈误报，等待有确认权限的人确认",
            "确认之前阻断保留。有确认权限的角色是：术语管理员、管理员、所有者。你也可以先重新生成修订版。",
        ),
        locate,
        revised,
    ]


def remedies_for(code: str, rule_class: str) -> list[dict[str, Any]]:
    """Ordered options for one finding. The API drops the ones this person or this task state cannot run.

    kinds: ``locate`` (show the page), ``disposition`` (``action`` + prefilled ``reason``), ``revise``
    (new version from the same configuration), ``recheck`` (run the checks again), ``termbase`` (open the
    vocabulary workbench). Exactly one option is marked ``recommended``.
    """
    locate = _remedy("locate", "locate", "先看问题所在的页面", "对照原文和译文，确认问题是否真实存在，再选下面的处理方式。")
    revise = _remedy(
        "revise", "revise", "重新生成修订版",
        "原版会保留。新版用同一套配置重新翻译并自动复检；数字、编号、否定这类问题多半是单次漏译或改写，重译后常会消失。",
    )
    if rule_class == C3:
        return [_remedy(
            "recheck", "recheck", "重新检查",
            "这是检查没有跑成，不代表译文有问题。服务恢复后重新检查即可得出结论。", recommended=True,
        )]
    if rule_class == C1:
        revise["recommended"] = True
        return [
            locate,
            revise,
            _remedy(
                "false_positive", "disposition", "我核对过，这是检查误报",
                "确认译文其实是正确的时使用。提交后需要有确认权限的人（术语管理员、管理员、所有者）确认才会放行。",
                action="report_false_positive", reason=_FALSE_POSITIVE_REASON,
            ),
        ]
    if rule_class == C2:
        return [
            locate,
            _remedy(
                "waive", "disposition", "确认没问题，带着交付",
                "你看过并认为可以接受时使用。一个复核人即可，理由会记入审计，之后可以撤销。",
                action="grant_waiver", reason=_WAIVER_REASONS.get(code, _DEFAULT_WAIVER_REASON), recommended=True,
            ),
            revise,
        ]
    if rule_class == C4:
        return [
            _remedy(
                "termbase", "termbase", "去术语工作台核对译名",
                "先确认词库里的批准译名是否正确，需要的话在那里改好；改好后再重新生成修订版。", recommended=True,
            ),
            {**revise, "label": "按批准译名重新生成修订版",
             "why": "原版会保留。新版会按当前批准的译名重新翻译并自动复检。"},
            _remedy(
                "waive", "disposition", "本文确需这样翻，带着交付",
                "上下文确实需要不同译法时使用。复核人写明理由即可，只作用于本文，不会写入共享词库。",
                action="grant_waiver", reason=_TERM_WAIVER_REASON,
            ),
        ]
    if rule_class == WARN:
        return [
            locate,
            _remedy(
                "acknowledge", "disposition", "已阅，不影响交付",
                "警告本身不阻断交付；确认已阅后会记入审计。",
                action="acknowledge", reason=_ACKNOWLEDGE_REASON, recommended=True,
            ),
        ]
    return []


# Findings store the class they were produced with. When a rule is deliberately reclassified, findings that
# were already stored (and sit at the gate right now) must follow it, or the change would only reach a task
# after somebody re-ran its checks.
RECLASSIFIED: dict[str, str] = {"TEXT_ENCODING_ARTIFACT": C2}


def effective_class(code: str, stored: str | None) -> str:
    """The class a finding is handled under: a deliberate reclassification wins over the stored value."""
    return RECLASSIFIED.get(code) or stored or rule_for(code).rule_class


def all_rules() -> list[RuleInfo]:
    return list(_RULES.values())


# ------------------------------------------------------------------------------------------------
# fingerprints: "is this the same problem as last round?"
# ------------------------------------------------------------------------------------------------


def fingerprint(code: str, object_id: str | None, evidence: dict[str, Any] | None, location: dict[str, Any] | None = None) -> str:
    """Stable identity of a finding across re-checks of the same output."""
    info = rule_for(code)
    evidence = evidence or {}
    parts: dict[str, Any] = {"code": code}
    if object_id:
        parts["object_id"] = object_id
    for key in info.identity_keys:
        if key in evidence:
            value = evidence[key]
            parts[key] = sorted(map(str, value)) if isinstance(value, (list, set, tuple)) else value
    if not info.identity_keys and location:
        anchors = location.get("anchors") or []
        if anchors:
            parts["anchor"] = {k: anchors[0].get(k) for k in ("side", "page", "paragraph")}
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------
# rule set version: changes whenever the registry or any rule implementation changes
# ------------------------------------------------------------------------------------------------

_RULE_FILES = (
    "pipeline/qa/engine.py",
    "pipeline/qa/pdf_inspect.py",
    "pipeline/qa/registry.py",
    "pipeline/ad_qa.py",
    "pipeline/ad_inspection.py",
    "pipeline/term_snapshot.py",
    "structure/text_sanitize.py",
)


@lru_cache(maxsize=1)
def rule_set_version() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parents[2]
    for relative in _RULE_FILES:
        path = root / relative
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(relative.encode("utf-8"))
    return f"qa-{digest.hexdigest()[:12]}"


# ------------------------------------------------------------------------------------------------
# disposition policy (who may do what with a finding of a given class)
# ------------------------------------------------------------------------------------------------

REVIEWER_ROLES = frozenset({"reviewer", "term_admin", "admin", "owner"})
CONFIRMER_ROLES = frozenset({"term_admin", "admin", "owner"})

#: action -> classes it applies to
ACTION_CLASSES: dict[str, frozenset[str]] = {
    "acknowledge": frozenset({WARN}),
    "report_false_positive": frozenset({C1, C2, C4, WARN}),
    "confirm_false_positive": frozenset({C1}),
    "reject_false_positive": frozenset({C1}),
    "grant_waiver": frozenset({C2, C4}),
    "revoke_waiver": frozenset({C2, C4}),
}


def allowed_actions(rule_class: str, role: str, *, is_writer: bool) -> list[str]:
    """Dispositions this caller may attempt on a finding of ``rule_class`` (server re-checks each)."""
    out: list[str] = []
    for action, classes in ACTION_CLASSES.items():
        if rule_class not in classes:
            continue
        if action in {"confirm_false_positive", "reject_false_positive"}:
            allowed = role in CONFIRMER_ROLES
        elif action in {"grant_waiver", "revoke_waiver"}:
            allowed = role in REVIEWER_ROLES
        elif action == "acknowledge":
            allowed = role in REVIEWER_ROLES or is_writer
        else:  # report_false_positive: any reviewer, or the submitter
            allowed = role in REVIEWER_ROLES or is_writer
        if allowed:
            out.append(action)
    return out
