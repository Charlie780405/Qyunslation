# PLAN-034d：概念型术语库

> 状态：**待编码**（骨架文档）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034d0](./PLAN-034d0-glossary-ssot-bridge.md)（必须先收敛扁平三分裂）

## 目标

以 **Concept** 为中心的术语库：首选词、同义词、缩写、禁用词、不翻译规则、领域、证据、许可证、状态、版本、批准人；支持作用域、审批、CSV/TBX；迁移现有 `glossaries/*.csv`。

## 数据模型（纲要）

```text
Concept
  ├── id, domain, status, version, license, evidence, approved_by, approved_at
  ├── preferred_term[lang]
  ├── synonyms[] / abbreviations[]
  ├── forbidden_translations[]
  ├── do_not_translate: bool / rules
  └── scope: org | form | clinical | project | tenant | session
```

优先级沿用 PLAN-039：`org > form > clinical > project > session > harvest`，映射到 Concept 作用域。

## 规则

1. LLM 自动提取 **只生成候选**，禁止自动发布为 curated。
2. MedDRA **仅企业自带授权数据**，禁止进入公共默认库或公开 git。
3. 导出兼容：运行时仍可生成 BabelDOC 所需的扁平 `merged.csv` 视图。
4. CSV/TBX 导入导出；导入默认进 staging，人工晋升。

## 判据

- 现有 370 条 curated 可迁移且双向抽查一致。
- 硬性术语命中率评测接口就绪（供 034a/034h 阈值使用）。
- 禁用译法检测：命中即失败。

## Out of Scope

- 审校 UI（→ 034g）
- 公开分发 MedDRA

## 完成定义

- [ ] Concept schema + 迁移脚本
- [ ] CSV/TBX + 扁平导出
- [ ] LLM 候选不自动发布的门禁测试
