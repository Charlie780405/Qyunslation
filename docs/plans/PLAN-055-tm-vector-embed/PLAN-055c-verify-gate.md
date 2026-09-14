# PLAN-055c：门禁

> 父计划：[PLAN-055](./PLAN-055-tm-vector-embed.md)

## 验收

```bash
bash scripts/verify-plan-055.sh
# 可选 LIVE：
# QYUNSLATION_PLAN055_LIVE=1 bash scripts/verify-plan-055.sh
```

| 组 | 判据 |
| --- | --- |
| 静态 | 文档 / MCP / client / 迁移 |
| pytest | client + semantic lookup（无网） |
| 泰州 | tags 含 bge-m3 + 一次 embed 维数 1024；不可达 → BLOCKED |
| LIVE | alembic + 近义句 semantic 非空 |

## 完成定义

- [x] `SUMMARY: PASS` 或明确 `BLOCKED`（泰州/LIVE），pytest 不 FAIL
