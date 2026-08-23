# PLAN-004：保质量再加速

## 目标

PLAN-003 已关自动抽术语、`qps=4`、`OLLAMA_NUM_PARALLEL=4`。本期在 **同一 35b-a3b、temp=0、BabelDOC** 下再挖：超大 ctx、无上限 `num_predict`、已是中文仍打模型、批阈值偏保守。不换模型、不换排版。

## 子计划进度

| 编号 | 名称 | 依赖 |
| --- | --- | --- |
| 004a | 推理卫生 | PLAN-003 |
| 004b | 跳过 + 术语表 + 缓存 | 004a |
| 004c | 上调 LLM 批阈值 | 004a（与 004b 可并行验收） |
| 004d | 同权重 vLLM（门禁） | 004a+b+c 未达 SLO 且 GPU 闲 |

## 质量不变量

- 模型 `qwen3.6:35b-a3b`、`temperature=0`、系统提示含 `/no_think`
- 抽检：QX027N QnA 第 1/中/末 3 页对照 Vault `DT-2026-0002`
- `il_translator_llm_only` JSON 失败 fallback 必须保留

## Out of Scope

- 换小模型 / 双模式 / MinerU 重排版 / 外发 DeepL
- 动 GPU1 HPD
- BabelDOC 链进 Qyunslation（AGPL）
- 未触发门禁就上 vLLM

## 总 SLO

| 阶段 | 速度 | 质量 |
| --- | --- | --- |
| 004a | 段均摊 ≤1.8s @4 | 1 页无漏段 |
| 004b | 热缓存再译 <2 min；首译少打已中文段 | 术语 ≥ DT-2026-0002 |
| 004c | QnA ≤10 min（门通过时） | fallback 不恶化 2× |
| 004d | 仅门禁 | 与 004c 抽检一致 |

## 实现顺序

1. 落盘 PLAN/verify
2. 004a → 004b → 004c
3. 未达 SLO 且 GPU 闲 → 才评估 004d
