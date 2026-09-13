# WT-034：医药研发翻译 MVP（总验收）

父计划：[PLAN-034](../plans/PLAN-034-pharma-rd-mvp/PLAN-034-pharma-rd-mvp.md)。

## 硬规则

**任一子门禁 FAIL 或 BLOCKED，不得宣称 PLAN-034 完成。**

## 子计划索引

| ID | WT | verify |
| --- | --- | --- |
| 034a/a1 | [WT-034a](./WT-034a-gold-benchmark.md) | `verify-plan-034a.sh` |
| 034b | [WT-034b](./WT-034b-semantic-policy.md) | `verify-plan-034b.sh` |
| 034c | [WT-034c](./WT-034c-saas-persistence.md) | `verify-plan-034c.sh` |
| 034d0 | [WT-034d0](./WT-034d0-glossary-ssot.md) | 伞门内 |
| 034d | [WT-034d](./WT-034d-concept-termbase.md) | `verify-plan-034d.sh` |
| 034e | [WT-034e](./WT-034e-translation-memory.md) | `verify-plan-034e.sh` |
| 034f | [WT-034f](./WT-034f-model-gateway-qa.md) | `verify-plan-034f.sh` |
| 034g | [WT-034g](./WT-034g-human-review-bench.md) | `verify-plan-034g.sh` |
| 034h | [WT-034h](./WT-034h-gold-saas-pilot.md) | `verify-plan-034h.sh` |

## 伞门

```bash
bash scripts/verify-plan-034.sh
```

## 已知限制

- 金标 PDF 不入库；本机 `GOLD_ROOT` / 合成物化。
- 全量 Pharma-MQM Critical=0 实跑需 `QYUNSLATION_PLAN034_GOLD_E2E=1` + 报告 JSON。
- Ollama 不可达时 034f 记 BLOCKED。
- PWA 仅缓存静态壳，不离线翻译。
- OIDC 生产需配置 issuer/audience/JWKS；不自动推 `main`。
