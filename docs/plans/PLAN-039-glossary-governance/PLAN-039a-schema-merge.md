# PLAN-039a：schema 与 merge

> 状态：**已完成**
> 父计划：[PLAN-039](./PLAN-039-glossary-governance.md)

## 交付

- CSV 头：`source,target,src_lng,tgt_lng,layer,domain,sponsor,status,notes`
- `qyunslation/glossary/governance.py`：load / normalize / merge_by_priority
- 优先级：`org > clinical > project > session > harvest`
- `scripts/verify-plan-039.sh` 骨架 + 单测

## 验收

```bash
bash scripts/verify-plan-039.sh
```
