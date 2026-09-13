# WT-034f：模型网关与医药 QA

对应 [PLAN-034f](../plans/PLAN-034-pharma-rd-mvp/PLAN-034f-model-gateway-qa.md)。

## 执行摘要

落地 `profiles.yaml` 三档（仅 `quality` 接线，基线 `qwen3.6:35b-a3b`）；`start_translation` 绑定档位且不覆盖用户 model；`Job.provenance` 去密钥写入；确定性 12 项 QA + 可选一轮 repair；`POST /api/v1/qa/run`。PDF 侧仅同步脚本投影 model id，**不**改 pdf2zh 进程内循环。向量检索 / TM 自动套用仍不做。

## 用法

```bash
export QYUNSLATION_GATEWAY_PROFILE=quality
export QYUNSLATION_BASE_URL='http://127.0.0.1:11434/v1'   # 示例，勿提交真实密钥
.venv/bin/python scripts/plan034f-sync-pdf2zh-model.py

# 迁移
.venv/bin/python -m alembic -c alembic.ini upgrade head

export QYUNSLATION_DEV_AUTH_BYPASS=1
curl -sS -H 'X-Dev-User: a' -H 'X-Dev-Tenant: t' \
  -H 'Content-Type: application/json' \
  -d '{"source_text":"Dose was 10 mg","target_text":"剂量丢失","role":"table"}' \
  http://127.0.0.1:8010/api/v1/qa/run
```

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/gateway/test_plan034f_gateway.py` | PASS |
| V2 | `bash scripts/verify-plan-034f.sh` | PASS；Ollama 不可达 → BLOCKED |
| V3 | provenance / 审计 | 无 api_key |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/gateway/*` | profiles / provider / risk / qa / pipeline |
| `qyunslation/persist/models.py` | `Job.provenance` |
| `alembic/versions/034f0001_*.py` | 迁移 |
| `qyunslation/api/v1.py` | provenance + `/qa/run` |
| `qyunslation/server/core.py` | `apply_gateway_profile` |
| `scripts/plan034f-sync-pdf2zh-model.py` | PDF 投影 |
| `scripts/verify-plan-034f.sh` | 门禁 |
