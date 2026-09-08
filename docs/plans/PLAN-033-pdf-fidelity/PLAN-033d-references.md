# PLAN-033d：参考文献区口径

> 状态：**已设计，未实施**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033a / 033b（计数与几何先稳）

## 目标

参考文献**标题**可译，**条目正文**保留原文。与「Enable auto term extraction」互斥：开术语采集时不得把参考文献条目当术语源。

## 不做什么

- 全文禁译任何含 `References` / 数字引用的句子（会误伤正文 `as shown in [12]`）
- 改术语表 CSV

## 做法（待施工）

1. 扫描器识别 `References` / `Bibliography` / `参考文献` 标题块，其后到页末或下一一级标题的条目标 `semantic_scope=references`。
2. 执行侧：标题走文字层翻译；条目 `planned_action=skip` 或 BabelDOC 保留。
3. 合成夹具：一页正文引用句 + 一页参考文献标题与两条条目。

## 验收

| # | 预期 |
| --- | --- |
| V1 | 标题可译、条目不译 |
| V2 | 正文 `see [12]` 仍译 |
| V3 | 术语采集不收录条目字符串 |
