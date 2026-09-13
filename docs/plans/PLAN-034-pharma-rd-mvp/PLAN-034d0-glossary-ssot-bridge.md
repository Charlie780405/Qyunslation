# PLAN-034d0：术语单一事实源收敛与 prompt 桥接

> 状态：**已实现**（文件层 SSOT + service 桥接；Concept 仍属 034d）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：034b（策略契约）、034c（持久化契约就绪后方可把 session 层写入库；本子项编码可先做文件层）
> 前置清理原因：不先收敛扁平术语三分裂，034d Concept 迁移会把分裂固化进新 schema
> 证据：[WT-034d0](../../walkthroughs/WT-034d0-glossary-ssot.md)

## 目标

让 PDF 链、Office 链、UI 增量术语读到**同一套** curated 合并结果；Office 翻译时按 chunk 命中过滤注入强指令 prompt；键规范化一致。

## 根因：术语三分裂

| 断点 | 现象 | 证据 |
| --- | --- | --- |
| **G1** | UI 增量进不了任何翻译链 | `server/core.py` 全仓不引用 `build_glossary_prompt`；`scripts/glossary_merge_runtime.py` 只读 CSV + harvest，不读 `glossary_db.json` |
| **G2** | Office/UI 路径少三层术语 | `glossary_db._load_l1_preset()` 只读 `clinical-lifecycle.csv`（`qyunslation/extensions/glossary_db.py`）；实测 `load_glossary()` **209** 条 vs `build_merged_dict()` **370** 条 |
| **G3** | 键规范化不一致 | `Glossary.__init__` 保原样大小写（`qyunslation/glossary/glossary.py`）；`Glossary.update` 用 `strip().lower()` |
| **G4** | 绕过规范化合并 | `markdown_agent.update_glossary_dict` 裸 `|` 合并（`qyunslation/agents/markdown_agent.py`） |

```text
4 层 curated CSV (370)
        │
        ▼
build_merged_dict() ──► merged.csv ──► PDF/BabelDOC ✓
        │
        ✗ 未接
        ▼
glossary_db (仅 clinical → 209) ◄── glossary_db.json (UI，现常为空)
        │
        ✗ server/core 从不调用
        ▼
Office 链拿不到 / 或仅靠用户上传 CSV → Glossary(chunk 命中)
```

## 对旧审计方案的修正

`docs/plans/cursor-import/交付断层与gpu审计_15b87189.plan.md` 曾建议把 `build_glossary_prompt()` **全表**硬指令注入 `custom_prompt`。

实测：`build_glossary_prompt(build_merged_dict())` ≈ **9429 字符**，按 chunk 全表注入每次约 3k token，吃上下文并拖慢。

**034d0 方案：** 保留中文强指令措辞，但**按当前 chunk 文本命中过滤**术语项（复用 `Glossary.append_system_prompt` 的 `src in text` 思路），只注入命中项。

## 实现步骤（编码阶段）

1. **`glossary_db._load_l1_preset()`** 改走 `build_merged_dict()`（四层全量），不再只读 clinical CSV。
2. **`glossary_db.json` → staging**：导出为 `glossaries/staging/ui-increment.csv`（`layer=session`），纳入 `glossary_merge_runtime.py`，使 UI 术语进入 `merged.csv` / PDF 链。
3. **桥接点在 service 层**：`qyunslation/server/core.py` 的 `start_translation`（不放 `app.py`）。原因：`/service/translate/file` 直收 `Json[TranslatePayload]`，不走 `/flat-translate` 的 payload_dict；只有 service 层能同时覆盖两入口。命中过滤后追加到 `payload.custom_prompt`（拼在用户自填之后），打注入条数日志。
4. **`Glossary._normalize_key()`**：`__init__` 与 `update` 同走；`markdown_agent.update_glossary_dict` 改调 `Glossary.update`。

## 判据

| # | 判据 |
| --- | --- |
| V1 | `load_glossary()` 条数与 `build_merged_dict()` 一致（± session 增量） |
| V2 | 文档中记录实测锚点：**370 vs 209**、全表 prompt **9429** 字符（历史对照；实现后全表不再默认注入） |
| V3 | 向 `glossary_db.json` 写入一条唯一术语 → 出现在 staging CSV / 下次 merge → Office 与 PDF 同译 |
| V4 | 同一 source 大小写变体只保留一条规范化键 |
| V5 | chunk 未命中时 prompt 不膨胀至全表长度 |
| V6 | `/service/translate` 与 `/service/translate/file` 均打到注入日志 |

## Out of Scope

- Concept 模型、TBX、审批工作流（→ 034d）
- 改 pdf2zh BabelDOC 内部 glossary 格式（继续读 merged.csv）
- MedDRA 入库

## 完成定义

- [x] 四步实现合入功能分支 `feat/PLAN-034-pharma-rd-mvp`
- [x] 单测覆盖规范化、命中过滤、service 双入口（经 `start_translation`）
- [x] `verify-plan-034.sh` 中 034d0 编码检查 PASS
