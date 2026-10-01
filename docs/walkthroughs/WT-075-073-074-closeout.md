# WT-075：073/074 收口与生产对齐

> 状态：**075 收尾完成；DeepSeek 与浏览器证据已就绪；全量金标机器译文仍为 BLOCKED 基线**

## 执行摘要

PLAN-075 合并 PLAN-074 至 `main`，完成 `074a0001` 迁移与部署对齐，引入部署三道门禁，补全 074 文档与真件回归脚本，新增外发审计 API，并将领域评测改为机器译文优先。

## 变更明细

| 子计划 | 交付 |
| --- | --- |
| 075a | `6915de3` 合并；备份 `qyunslation-pre-074a-20261001T205548Z.dump`；Alembic `074a0001` |
| 075b | `deploy_gate.py` + `deploy-translate-stack.sh` pre/post |
| 075c | PLAN-074 文档；`plan074-live-regression.py`；WT-074 |
| 075d | `GET /admin/egress-audit`；`translation_run.egress` 审计 |
| 075e | `plan073-domain-eval.py` v2；`domain-autoimmune.csv` 35 条；dupilumab `machine.zh.txt` |

## 验证

```bash
bash scripts/verify-plan-075.sh
bash scripts/verify-plan-074.sh
bash scripts/verify-plan-073.sh
```

## 生产（2026-10-02）

| 步骤 | 结果 |
| --- | --- |
| Git | `main` @ `6915de3`+（075 补丁） |
| Alembic | **`074a0001`** |
| API 冒烟 | `affiliation-segments` / `apply-corrections` → **401** |
| Live regression | 术语金标 PASS；legacy dual PDF QA → **BLOCKED**（需 PLAN-074 重跑） |
| Domain eval | 1/10 样本有机器译文；9 样本 **BLOCKED**（真实基线） |

## 075 收尾（2026-10-02）

| 项 | 结果 |
| --- | --- |
| Chromium | `scripts/install-headless-chromium.sh` → `~/.local/bin/chromium` |
| 浏览器证据 | `scripts/capture-plan073-074-evidence.py` → `docs/evidence/plan073-074/*.png`（4 张） |
| DeepSeek | `QYUNSLATION_DEEPSEEK_API_KEY` 已写入 `office.env`；`deepseek_configured()` PASS |

## 仍 BLOCKED（预期基线）

1. 用 PLAN-074 流水线重跑 Dupilumab Poster，使 live regression QA 段 PASS。
2. 为其余 9 份金标样本补充 `machine.zh.txt` 后领域评测方可全绿。
3. 可选：用 `public-deepseek-flash` 跑一份公开资料全文翻译留痕。
