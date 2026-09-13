# PLAN-034e：翻译记忆与上下文

> 状态：**已编码**（精确复用 + 模糊建议 + TMX；无向量检索）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034c](./PLAN-034c-saas-persistence.md)、[034d](./PLAN-034d-concept-termbase.md)
> 历史：**关闭 PLAN-001d4**「TM 精确匹配层待执行」——精确匹配由本计划交付；向量/相似句检索仍不在范围内
> 验收门：`bash scripts/verify-plan-034e.sh`
> Walkthrough：[WT-034e](../../walkthroughs/WT-034e-translation-memory.md)

## 目标

建设正式翻译记忆（TM）：只有**已批准**句段入库；精确匹配可复用；模糊匹配仅上下文/人工建议；支持 TMX；与术语库分库分版本。

## 硬规则

| 规则 | 说明 |
| --- | --- |
| 表 | `tm_unit`（与 concept **分表**）；整型 `version`，无版本子表 |
| 入库 | 仅 `approved=true`；`POST /api/v1/tm/units` 须显式批准（模拟 034g）；缺省 400 |
| 精确匹配 | `source_norm` 相等 **且** `placeholder_sig` 相等 → `reuse=true` |
| 模糊匹配 | `difflib.SequenceMatcher` ≥0.85；`reuse=false`，仅 `suggestions[]` |
| 作用域 | `tenant_id` + 可选 `project_id`；禁止跨租户 |
| TMX | 导入默认 `approved=false`；导出仅 approved |
| 执行桥 | **不**改 BabelDOC / `start_translation` 自动套用 |

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/tm/units` | 批准入库（upsert 去重） |
| POST | `/api/v1/tm/lookup` | 精确 / 模糊查询 |
| GET | `/api/v1/tm/export.tmx` | 导出已批准 |
| POST | `/api/v1/tm/import.tmx` | 导入为未批准 |

## 判据

- 未批准句段不进正式 TM。
- 精确命中且签名一致 → 复用；签名不一致 → 不复用。
- 模糊命中不直接写译文。
- TMX round-trip 抽样通过。

## Out of Scope

- 向量语义检索
- 计费与配额
- 034g 审校 UI
- BabelDOC 自动套用

## 完成定义

- [x] TM 表 + 精确/模糊 API
- [x] 批准门禁测试
- [x] TMX 导入导出
- [x] 文档关闭 001d4 悬空说明
