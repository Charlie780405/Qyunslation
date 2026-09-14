# PLAN-055b：TM 语义建议

> 父计划：[PLAN-055](./PLAN-055-tm-vector-embed.md)

## 目标

同一 HTTP 契约的 `embed/client.py`；旁路表 `tm_unit_embedding`；`lookup` 增加 `semantic_suggestions`（`reuse` 仍仅精确）。

## 交付

1. `qyunslation/embed/client.py` + pytest mock
2. Alembic `055a0001` → `tm_unit_embedding`；`create_approved_unit` 同步 embed（失败不挡）
3. `lookup`：精确 → 向量建议 → 模糊；阈值 `QYUNSLATION_TM_SEMANTIC_THRESHOLD` 默认 0.88

## 完成定义

- [x] 精确仍 `reuse=true`；语义只进 `semantic_suggestions`
- [x] embed 失败降级模糊，不 500
