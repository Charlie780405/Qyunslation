# PLAN-055：TM 向量 + 泰州 bge-m3 MCP

> 状态：**完成**
> 日期：2026-09-13
> 依赖：PLAN-034e（TM 精确/模糊）、PLAN-054（OIDC）；泰州 Ollama bge-m3
> 验收门：`bash scripts/verify-plan-055.sh`
> Walkthrough：[WT-055](../../walkthroughs/WT-055-tm-vector-embed.md)

## 一句话

把泰州 `bge-m3` `/api/embed` 包装成 Hermes 薄层 MCP 供多项目复用；qyunslation TM lookup 增加语义建议，**精确命中仍是唯一 `reuse=true`**。

## 共享契约

| 项 | 值 |
| --- | --- |
| URL | `{OLLAMA_EMBED_URL}/api/embed` |
| 默认 URL | `http://100.67.66.123:11434` |
| 模型 | `OLLAMA_EMBED_MODEL` 默认 `bge-m3` |
| 维数 | `OLLAMA_EMBED_DIM` 默认 `1024` |
| 超时 | `OLLAMA_EMBED_TIMEOUT` 默认 `30` |
| 请求 | `{"model": str, "input": list[str]}`（1–32 条） |
| 响应 | `{"embeddings": [[floats...]], ...}` |

## 子计划

| ID | 交付 |
| --- | --- |
| [055a](./PLAN-055a-embed-mcp.md) | Hermes `embed-mcp` + 注册 |
| [055b](./PLAN-055b-tm-semantic.md) | client + `tm_unit_embedding` + semantic lookup |
| [055c](./PLAN-055c-verify-gate.md) | verify-055 三态门禁 |

## Out of Scope

- 向量命中 `reuse=true` / BabelDOC 自动套用
- knowledge 改走本 MCP（仍 `vault_search.py --rerank`）
- TEI / OpenAI `/v1/embeddings` / pgvector 换镜像
- 审校台 PKCE、自动 enqueue

## 完成定义

- [x] 纲领 + 055a/b/c + README + WT-055；plans 索引与 051/054 回链
- [x] Hermes embed-mcp 可 stdio 冒烟
- [x] TM semantic_suggestions；reuse 仅精确
- [x] `verify-plan-055.sh` 静态+pytest PASS；泰州不通 → BLOCKED
