# PLAN-055a：公共 Embedding MCP（Hermes）

> 父计划：[PLAN-055](./PLAN-055-tm-vector-embed.md)

## 目标

stdio JSON-RPC MCP（仿 `hpd-mcp`），工具 `embed_texts` / `embed_health`，代理泰州 Ollama `/api/embed`。

## 交付

| 路径 | 说明 |
| --- | --- |
| `/home/dev/Hermes/mcp/embed-mcp/server.py` | MCP 服务 |
| `/home/dev/Hermes/mcp/embed-mcp/README.md` | 契约与边界 |
| Hermes `.cursor/mcp.json` + `servers.yaml.example` | 注册 |
| qyunslation `.cursor/mcp.json` | 指针（不复制实现） |

## env

`OLLAMA_EMBED_URL` / `OLLAMA_EMBED_MODEL` / `OLLAMA_EMBED_DIM` / `OLLAMA_EMBED_TIMEOUT`

## 不做

- 不暴露 Chroma / vault_search / rerank
- 不改 `vault_search.py` 硬编码

## 完成定义

- [x] `embed_health` / `embed_texts` 可用；泰州不可达返回 JSON error 不崩进程
