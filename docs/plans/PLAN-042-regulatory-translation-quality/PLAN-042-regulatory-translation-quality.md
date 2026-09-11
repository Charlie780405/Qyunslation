# PLAN-042：临床监管表单译文质量收口

> 状态：**已完成**
> 日期：2026-09-11
> 分支：`feat/PLAN-042-regulatory-translation-quality`
> 批准记录：用户确认 Cursor 计划「PLAN-042 译文质量收口」后实施
> 验收门：`bash scripts/verify-plan-042.sh`；证据汇总写入 [WT-042](../../walkthroughs/WT-042-regulatory-translation-quality.md)
> 前置：PLAN-041 表格链与硬门禁已合入；本计划收口 BabelDOC 回退路径上的译文质量与交付可见性

## 一、问题结论

CTR20231233 登记表对照截图上的缺陷**绝大多数不是 041 单元格链产出**，而是表格链失败后静默回退到 BabelDOC 段落路径的产物：

1. `min_text_length = 5` 导致 1–4 字值格全量未译。
2. BabelDOC typesetting 字符级重排造成英文词内断裂与拼写损坏。
3. `paragraph_finder` 跨单元格纵向合并，标签/值错配、机构名与人名并入同格。
4. 受控实体词表无中国医院/申办方官方英文名，模型自由猜译。
5. 表格链硬失败只写 Manifest，GUI 仍报成功并交付坏版式。

错误台账见 [error-taxonomy.md](./error-taxonomy.md)（24 类 / 7 族）。

## 二、目标

- 短标签与登记表固定字段零漏译，且不冲击 PLAN-003/004 吞吐门。
- 拉丁词零词内断裂；标签与值零行偏移；跨单元格合并为零。
- 申办方/医院/院校/人名命中受控层或显式保留原文，零幻觉词。
- 表格链任一硬失败时 GUI 告警并附逐格清单（告警交付，不阻断）。
- 字号下限与整页中文残留升为全文级指标门。

## 三、子计划

| 编号 | 文件 | 交付 |
| --- | --- | --- |
| [042a](./PLAN-042a-taxonomy-fixtures.md) | 台账与夹具 | 24 类台账、合成夹具、回归底座 |
| [042b](./PLAN-042b-short-label-direct.md) | 短标签直译 | 登记表字段词表层 + BabelDOC 译前精确直替 |
| [042c](./PLAN-042c-word-break.md) | 断词约束 | regulatory 画像英文整词换行、禁止边界插空格 |
| [042d](./PLAN-042d-cell-attribution.md) | 单元格归属 | bbox 约束、全量 redaction、标签-值配对断言 |
| [042e](./PLAN-042e-controlled-entities.md) | 受控实体 | 机构/人名/章节序号/量词确定性映射 |
| [042f](./PLAN-042f-warn-delivery.md) | 告警交付 | QC sidecar、GUI 告警、全文门、verify-042 |

## 四、验收口径

见各子计划与父计划 Cursor 计划 §四。

## 五、非目标

- 不重写 BabelDOC 版式引擎。
- 不引入 MedDRA/WHO-DD 全量词库。
- 不改为阻断交付。
- 不提交实样 PDF/截图/个人信息；实样经 `QYUNSLATION_PLAN042_SAMPLE`。
- 不动 `glossaries/auto-proper-nouns.csv` 运行时产物。

## 六、完成定义

- [x] 042a–042f 全部通过
- [x] `scripts/verify-plan-042.sh` PASS（缺实样可 BLOCKED）
- [x] WT-042 写明证据
- [x] SK-Q003 扩写
- [x] no-ff 合入 `main` 并部署
