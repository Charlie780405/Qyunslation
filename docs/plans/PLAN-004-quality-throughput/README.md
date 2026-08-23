# PLAN-004 保质量再加速

在 PLAN-003（关术语轮、qps=4、OLLAMA_NUM_PARALLEL=4）之上，同一 `qwen3.6:35b-a3b`、temp=0、BabelDOC 链继续挖吞吐。

| 文件 | 作用 |
| --- | --- |
| `PLAN-004-quality-throughput.md` | 纲领 |
| `PLAN-004a-inference-hygiene.md` | ctx / num_predict 推理卫生 |
| `PLAN-004b-skip-glossary-cache.md` | 跳过已目标语 + QX027 术语表 + 缓存可观测 |
| `PLAN-004c-llm-batch.md` | LLM 批阈值 400/8 + fallback 门禁 |
| `PLAN-004d-vllm-gate.md` | 同权重 vLLM（默认不做，门禁触发） |

verify：`scripts/verify-plan-004.sh`（阶段 `baseline | after-a | after-b | after-c`）

WT：`docs/walkthroughs/WT-004-*.md`
