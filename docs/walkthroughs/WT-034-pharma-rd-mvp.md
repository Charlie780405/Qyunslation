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
- 034h 金标门跑 034a 目录骨架评估，不是整本 Pharma-MQM 重译。
- **产品完成线（整本 Pharma-MQM）改看 [PLAN-051](../plans/PLAN-051-gold-pharma-mqm/PLAN-051-gold-pharma-mqm.md) / [WT-051](./WT-051-gold-pharma-mqm.md)**；真件补齐见 [WT-052](./WT-052-gold-real-fill.md)（本机 R-01 M2.5 已 promote）。
- Ollama 不可达时 034f 记 BLOCKED；本机 `.env` 的 endpoint 会被 verify 读取。
- PWA 仅缓存静态壳，不离线翻译。
- OIDC 生产需配置 issuer/audience/JWKS；不自动推 `main`。
