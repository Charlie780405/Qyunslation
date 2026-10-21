# PLAN-086：术语库、错法表与风格指南质量系统

> 状态：**核心闭环已实现，待部署与专家金标验收**。实现内容包括版本化语言资产、受控人工导入、发布/回滚基础、翻译任务 bundle 快照、确定性错法 QA 和统一资产中心入口。

| 子计划 | 状态 | 交付 |
| --- | --- | --- |
| 086a 契约与基线 | 已完成 | 资产类型、作用域、版本、许可、哈希和 QA 门定义 |
| 086b 发布基础与导入 | 已完成 | Alembic、发布快照、CSV/TSV/TBX-Basic 预览/应用/幂等 |
| 086c 风格指南 | 已完成 | StyleProfile、发布版本、按语言/文档类型选择 |
| 086d 错法表 | 已完成 | QualityRuleDefinition、pitfall release、确定性触发 QA |
| 086e bundle 与任务接入 | 已完成 | `settings_snapshot.language_assets` 固定 bundle/hash |
| 086f QA 联动 | 已完成 | 数据驱动错法命中，沿用既有 QA 处置与审计 |
| 086g 统一资产中心 | 已完成 | `/termbase` 增加术语/风格/错法/发布视图和导入预览 |
| 086h 金标与灰度 | 待执行 | 专家盲评、上线前门禁、shadow→pilot→on |

执行证据见 [PLAN-086-language-assets-quality-system.md](./PLAN-086-language-assets-quality-system.md)。
