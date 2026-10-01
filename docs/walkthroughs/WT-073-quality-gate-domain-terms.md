# WT-073：质量门禁真实化、模型分级与自免术语闭环

> 状态：**工程闭环；DeepSeek/浏览器证据 BLOCKED**

## 执行摘要

PLAN-073 修复「卡在保存 PDF」的误报根因（术语 QA 误匹配），合并重复进度区，让资料等级驱动 pdf2zh 运行时配置，并在 `/next` 接入术语译前注入与译后抽取。

## 变更明细

| 区域 | 交付 |
| --- | --- |
| 073a | 主列进度摘要；右侧唯一时间线；qa_blocked 状态文案 |
| 073b | 区分大小写匹配；requalify 端点 |
| 073c | `runtime_config.py`；前端 model_profile_id |
| 073d | `term_inject.py` / `term_extract.py`；RunDetail 新术语面板 |
| 073e | `domain-autoimmune.csv`；金标目录；`plan073-domain-eval.py` |

## 验证

```bash
bash scripts/verify-plan-073.sh
```

- pytest plan073 — PASS
- domain eval — PASS（样本数随 gold 目录增长）
- DeepSeek 密钥 — BLOCKED（未配置时）
- 浏览器 qa_blocked 手测 — BLOCKED

## 生产发布（2026-10-01）

| 步骤 | 结果 |
| --- | --- |
| 备份 | `/home/dev/pdf2zh/backups/qyunslation-pre-073a-20261001T045410Z.dump` |
| Alembic | `072a0001` → **`073a0001`** |
| 部署 | sidecar 指纹 `7542777de0fd` 一致 |
| requalify | 任务 `65ecd028…`：`qa_blocked` → **`review_ready`**（blocker 0） |
| verify | `SUMMARY: BLOCKED fail=0 blocked=2`（DeepSeek/浏览器） |

## 领先判据

术语准确率 ≥98%、药名漂移 0、QA 误报 ≤1/文档（见 `var/plan073-domain-eval.json`）。
