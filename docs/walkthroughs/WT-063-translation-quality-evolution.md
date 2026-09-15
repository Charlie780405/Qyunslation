# WT-063：规则自动进化与全局质量总纲

> 计划：[PLAN-063](../plans/PLAN-063-translation-quality-evolution/README.md)

## 工程验证

| 项目 | 结果 |
| --- | --- |
| 机器裁决入 `TermDecision` | purge 改走 `decide_candidate`；现场回填 `plan062-purge` **165** 行 |
| `term-exclusions.csv` + `063-v1` | fingerprint `45b0012ae64d` 已登记 |
| `--screen-pending` | 只读提案：`EASI-50`/`EASI-90` → EASI 别名；`anti-tralokinumab` → tralokinumab |
| `excluded_stats` 迁移 | 生产库 `alembic upgrade 063a0001` 已执行 |
| ledger `SCREEN_BLIND` | `origin=error` 或 generic 占比过高即失明 |
| batch-approve 不放行 `violation` | 060/063 测试改为 400 |
| SK-Q011 + 六条签名 | registry 已补登 SK-Q010/Q011 |
| `verify-plan-063.sh` | **BLOCKED blocked=1 fail=0**（062 LIVE 待真实文档） |

## 本地命令

```bash
bash scripts/verify-plan-063.sh
# FULL 依赖门（含 062 LIVE）才会 BLOCKED/PASS 三项：
QYUNSLATION_PLAN063_FULL=1 bash scripts/verify-plan-063.sh
```

## PLAN-062 LIVE

进度条、保存下一条、Concept 下拉三项仍待真实文档补证，见 [WT-062](./WT-062-termbase-evolution.md)。本 WT 不把未补证写成已部署完成。

## 部署

规则与 sidecar 指纹无关。若要让 `excluded_stats` 列生效，需在生产库执行 `alembic upgrade head` 后 `bash scripts/deploy-translate-stack.sh`。
