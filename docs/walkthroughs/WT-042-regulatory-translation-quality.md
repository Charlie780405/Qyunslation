# WT-042：临床监管表单译文质量收口

日期：2026-09-11
纲领：[PLAN-042](../plans/PLAN-042-regulatory-translation-quality/PLAN-042-regulatory-translation-quality.md)
分支：`feat/PLAN-042-regulatory-translation-quality`

## 基线

| 指标 | 修复前 |
| --- | --- |
| 证据 | CTR20231233 登记表 5 页对照截图（不入库） |
| 短值格 | `min_text_length=5` 导致 1–4 字值格全量未译 |
| 断词 | BabelDOC typesetting 词内断裂（sc ore / Mono-Long） |
| 实体 | org 词表无中国医院/三生国健官方英文名 |
| 交付 | 表格链硬失败静默回退，GUI 仍报成功 |

## 实施记录

| 子计划 | 状态 | 证据 |
| --- | --- | --- |
| 042a | 已完成 | error-taxonomy 24 类；`plan042_fixtures.py` 合成夹具 |
| 042b | 已完成 | `regulatory-form-fields.csv` + form 层优先级 90；`apply-pdf2zh-042b-short-label.py` |
| 042c | 已完成 | `patch_regulatory_typesetting`；docprofile 在 regulatory 路径启用 |
| 042d | 已完成 | `table_attribution.py`；redaction pad；QC 码进硬门禁 |
| 042e | 已完成 | org 扩写 3SBio/医院；章节序号与 Phase II 确定性映射；表格链受控直替 |
| 042f | 已完成 | `execution_table_fidelity_hint` 告警汇总；`page_qc.py`；verify-042 |

## 门禁结果

| 门禁 | 结果 |
| --- | --- |
| verify-plan-042 | 见部署记录（缺实样 BLOCKED 可接受） |
| 042 + 041d + 037 + 039 聚焦测试 | 本地 PASS |

## 安全与数据

- 截图与实样不入库；实样经 `QYUNSLATION_PLAN042_SAMPLE`。
- 未提交 `auto-proper-nouns.csv` 运行时产物。

## 部署

| 项 | 值 |
| --- | --- |
| merge | （待填） |
| 服务 | `pdf2zh.service` 含 042b ExecStartPre |
| 补丁序 | 29 = `apply-pdf2zh-042b-short-label.py` |

## 遗留 / 下阶段输入

- [ ] 补 CTR20231233 原件后设 `QYUNSLATION_PLAN042_SAMPLE` 跑全文金标，确认表格链是未检出还是硬失败（→ 若未检出则加强 042d 扫描）
- [ ] 生产 GUI 手测：故意失败一表时进度文案须含「N 个表格未保真」
- [ ] 断词补丁依赖 BabelDOC 内部 API，升级 BabelDOC 后须重跑 `apply-pdf2zh-docprofile` + 042c 断言
