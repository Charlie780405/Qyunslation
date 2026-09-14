# PLAN-051c：门禁与 WT

> 状态：**已实现**
> 父计划：[PLAN-051](./PLAN-051-gold-pharma-mqm.md)
> 依赖：051a、051b
> 验收：`bash scripts/verify-plan-051.sh` → `SUMMARY: PASS`（无 LIVE）

## 目标

默认可在无 GPU 下 PASS；整本实跑 opt-in；缺条件 BLOCKED；质量差 FAIL。

## 交付

| 路径 | 说明 |
| --- | --- |
| `scripts/verify-plan-051.sh` | PASS/FAIL/BLOCKED + SUMMARY |
| `docs/walkthroughs/WT-051-gold-pharma-mqm.md` | 用法与两道门 |
| `docs/plans/README.md` | 索引一行 |

## 默认（每次）

1. 计划/WT/入口脚本存在
2. `pytest tests/gold/test_plan051a_run.py tests/gold/test_plan051b_score.py`
3. scorer 拒 skeleton
4. **不**调 `pdf2zh_next`

## LIVE（`QYUNSLATION_PLAN051_LIVE=1`）

1. catalog 完备；Ollama 探测失败 → BLOCKED
2. `plan051-run-gold.py`（`QYUNSLATION_PLAN051_LIMIT` 可选）
3. score → evaluate；fail → **FAIL**
4. `per_class_real.R == 0` → `product=BLOCKED`；总 SUMMARY 用 BLOCKED

034h 保持 skeleton。WT-034 注明产品完成改看 051 产品门。

## 判据

- 无 LIVE：`SUMMARY: PASS fail=0`
- LIVE + Ollama 挂：`SUMMARY: BLOCKED`
- 金标 PDF 不进 git
