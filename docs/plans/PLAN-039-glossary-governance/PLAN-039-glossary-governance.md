# PLAN-039：临床与专名术语治理

> 状态：**已完成**
> 日期：2026-09-10
> 批准记录：用户确认 Cursor 计划「PLAN-039 术语治理」后实施
> 验收门：`bash scripts/verify-plan-039.sh`；总览 [WT-039](../../walkthroughs/WT-039-glossary-governance.md)
> 前置：PLAN-010d 专名表、PLAN-038g 接通默认 `--glossaries`（未做治理）

## 一、目标

1. **一层架构**：词条有 `layer / domain / lang / status`；冲突按优先级，人工永不被 harvest/自动抽词覆盖。
2. **专属名词（L0）**：机构、品牌、产品代号、人名；景行/荃信/IQVIA/FDA 等可双向钉死。
3. **生命周期词库（L1）**：按医药开发域分层，保证专业译法稳定。
4. **可丰富**：候选 → staging 待审 → 晋升 L0/L1/L2。
5. **一处消费**：pdf2zh `--glossaries` 与 sidecar `load_static_glossary` 读同一合并结果。

## 二、子计划矩阵

| 编号 | 文件 | 交付 | 顺序 |
| --- | --- | --- | --- |
| [039a](./PLAN-039a-schema-merge.md) | schema + merge | 契约、优先级、verify 骨架 | 1 |
| [039b](./PLAN-039b-org-proper-nouns.md) | L0 专名 | 清洗 + 景行↔GenScend 等种子 | 2 |
| [039c](./PLAN-039c-clinical-lexicon.md) | L1 临床词库 | 生命周期种子，迁出 PRESET | 3 |
| [039d](./PLAN-039d-enrich-promote.md) | 挖词晋升 | staging CSV + promote CLI | 4 |
| [039e](./PLAN-039e-runtime-merge.md) | 运行时并表 | merged.csv 同供 GUI/sidecar | 5 |
| [039f](./PLAN-039f-docs-closure.md) | 文档收口 | WT-039、回写 010d/038g | 6 |

## 三、词条契约

见 [039a](./PLAN-039a-schema-merge.md)。合并优先级：**org > clinical > project > session > harvest**。

## 四、非目标

- 不引入完整 MedDRA/WHO-DD
- 不做独立术语后台 Web
- 不提交 `glossaries/auto-proper-nouns.csv` / staging
- 不把密码写入词表或 git
- 不重新打开 BabelDOC `no_auto_extract_glossary=false`

## 五、完成定义

- [x] 纲领+子计划齐
- [x] 合并优先级单测；景行→GenScend；GenScend 不被译成金斯瑞
- [x] pdf2zh 与 sidecar 对同一 source 得同一 target
- [x] `verify-plan-039.sh` 进 `verify-release.sh`
