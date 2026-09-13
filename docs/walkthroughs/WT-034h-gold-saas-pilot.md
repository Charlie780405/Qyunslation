# WT-034h：金标 SaaS 试点

对应 [PLAN-034h](../plans/PLAN-034-pharma-rd-mvp/PLAN-034h-gold-saas-pilot.md)。总览见 [WT-034](./WT-034-pharma-rd-mvp.md)。

## 执行摘要

收口 OIDC（JWT/JWKS）与 Dev 旁路互斥；最小 PWA 壳；发布指纹清单；SaaS API 烟囱；端到端门禁 `verify-plan-034h.sh`。金标全量 Critical=0 实跑需 `QYUNSLATION_PLAN034_GOLD_E2E=1`，否则记 BLOCKED。

## OIDC 环境变量

| 变量 | 说明 |
| --- | --- |
| `QYUNSLATION_ENV=production` | 强制 OIDC；Dev 旁路 403 |
| `QYUNSLATION_OIDC_ISSUER` | iss |
| `QYUNSLATION_OIDC_AUDIENCE` | aud |
| `QYUNSLATION_OIDC_JWKS_URL` | JWKS |
| `QYUNSLATION_OIDC_TENANT_CLAIM` | 默认 `tenant` |

勿把客户端密钥写入 git。

## 发布 / 回滚

```bash
bash scripts/plan034h-release-checklist.sh --write
bash scripts/deploy-translate-stack.sh
# 回滚：git checkout <prev-sha> → checklist --write → deploy-translate-stack.sh
```

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/persist/test_plan034h_*.py` | PASS |
| V2 | `bash scripts/verify-plan-034h.sh` | PASS 或 BLOCKED（金标） |
| V3 | production + bypass | 403 |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/persist/identity.py` | OIDC JWT/JWKS |
| `qyunslation/static/manifest.webmanifest` / `sw-034h.js` | PWA |
| `scripts/plan034h-release-checklist.sh` | 发布指纹 |
| `scripts/verify-plan-034h.sh` | 门禁 |
