# PLAN-045：学术文献 PDF 译文保真

> 状态：**已实现**（含译后强制术语 / 文献表 isolate 热修；须重译验收）
> 日期：2026-09-11
> 前置：[PLAN-033h](../PLAN-033-pdf-fidelity/PLAN-033h-references-body-style.md)、[PLAN-033k](../PLAN-033-pdf-fidelity/PLAN-033k-image-fit-qc.md)、[PLAN-039](../PLAN-039-glossary-governance/)、[PLAN-044](../PLAN-044-regulatory-layout-normalize/)
> Skill：[SK-Q002](../../../.cursor/skills/image-overlay-translation/SKILL.md)
> 验收：`bash scripts/verify-plan-045.sh`；证据 [WT-045](../../walkthroughs/WT-045-literature-pdf-fidelity.md)

## 目标

在不换 `qwen3.6:35b-a3b` 的前提下，收口学术文献路径上的：专业终点术语、参考文献误译、IL `<span>` 乱码、插图底擦/面板字母/字号、文献表字号分裂。

## Out of Scope

- 换模型；重开 044 监管表单软门；MedDRA 全库；重写 BabelDOC 排版引擎；实样入库。

## 子计划

| ID | 交付 |
| --- | --- |
| [045a](./PLAN-045a-clinical-lexicon.md) | L1 终点短语 + 图片默认 merged |
| [045b](./PLAN-045b-references-glued.md) | 粘连序号 ENTRY_RE + 033h 健康 |
| [045c](./PLAN-045c-il-sanitize.md) | IL span 消毒 + 叠印检测 |
| [045d](./PLAN-045d-image-panel-size.md) | panel_letter / k 下限 / 擦除 2 轮 |
| [045e](./PLAN-045e-literature-table-size.md) | 文献表 source_p75 |
| [045f](./PLAN-045f-verify-docs.md) | verify / Skill / WT |

## 实样

`QYUNSLATION_PLAN045_SAMPLE`（曲罗芦单抗/ECZTRA 类文献，仓库外）。
