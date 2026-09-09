# PLAN-033d：参考文献区口径

> 状态：**已完成**（`verify-plan-033d.sh` PASS）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033a / 033b（计数与几何先稳）

## 目标

参考文献**标题**可译，**条目正文**保留原文。与「Enable auto term extraction」互斥：开术语采集时不得把参考文献条目当术语源。

## 不做什么

- 全文禁译任何含 `References` / 数字引用的句子（会误伤正文 `as shown in [12]`）
- 改术语表 CSV

## 做法

1. `references.py`：独立标题行才算区首；`see [12]` 不是条目。
2. 扫描器：标题后（含跨页）的 BODY 标 `semantic_scope=references`、`planned_action=skip`。标题本身仍 `babeldoc_text_layer`。
3. `proper_nouns.harvest` 丢掉条目文本，不改 CSV。
4. 合成夹具 `references-section.pdf`。扫描器 `1.4.0`。

## 验收

| # | 预期 |
| --- | --- |
| V1 | 标题可译、条目不译 |
| V2 | 正文 `see [12]` 仍译 |
| V3 | 术语采集不收录条目字符串 |
