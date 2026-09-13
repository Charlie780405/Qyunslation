# PLAN-034d：概念型术语库

> 状态：**已实现**
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034d0](./PLAN-034d0-glossary-ssot-bridge.md)、[034c](./PLAN-034c-saas-persistence.md)
> 证据：[WT-034d](../../walkthroughs/WT-034d-concept-termbase.md)
> 验收：`bash scripts/verify-plan-034d.sh`

## 目标

以 **Concept** 为中心的术语库：首选词、同义词、缩写、禁用词、不翻译规则、领域、证据、许可证、状态、版本；支持作用域层、CSV 导入、扁平导出给 034d0/BabelDOC。

## 数据模型

```text
concept / concept_term / concept_forbidden
```

- `status`: `curated` | `staging` | `rejected`
- `layer`: 映射 PLAN-039（org > form > clinical > project > session > harvest）
- `POST /api/v1/concepts` **强制 staging**（LLM 候选不自动发布）

## 规则

1. LLM / API 写入只进 staging。
2. MedDRA **禁止**公共默认库或公开 git。
3. 无 `DATABASE_URL` 时 `build_merged_dict` 仍走 CSV（034d0 不回归）。
4. 有库且含 curated 时优先 Concept 扁平视图，再叠 session/harvest 文件。
5. TBX：本期仅导出 stub（`concept_flatten.write_tbx`）。

## 判据

- curated CSV 可幂等导入；`景行生物` → `GenScend` 抽查一致。
- `detect_forbidden` 纯函数可用。
- staging 不进入 flatten curated 视图。

## Out of Scope

- 审校 UI（→ 034g）
- TM / TMX（→ 034e）
- 公开分发 MedDRA；TBX 完整导入

## 完成定义

- [x] Concept schema + Alembic `034d0001`
- [x] CSV 导入 + 扁平导出接入 `build_merged_dict`
- [x] LLM/API 候选不自动发布的门禁测试
