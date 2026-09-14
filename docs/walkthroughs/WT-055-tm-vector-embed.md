# WT-055：TM 向量 + 泰州 bge-m3 MCP

对应 [PLAN-055](../plans/PLAN-055-tm-vector-embed/PLAN-055-tm-vector-embed.md)。

**状态：完成**（`verify-plan-055.sh` → `SUMMARY: PASS fail=0`，2026-09-13）

## 执行摘要

1. Hermes `mcp/embed-mcp` 代理泰州 `POST /api/embed`（bge-m3 / 1024 维）
2. qyunslation `embed/client.py` 同契约
3. `tm_unit_embedding` 旁路表；批准时写入向量
4. `/tm/lookup` 增加 `semantic_suggestions`；**只有精确命中 `reuse=true`**

## 验证

```bash
bash scripts/verify-plan-055.sh
# 可选 LIVE：
# QYUNSLATION_PLAN055_LIVE=1 bash scripts/verify-plan-055.sh
```

泰州不可达 → 探活 **BLOCKED**（pytest 仍须绿）。

## MCP 冒烟

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"embed_health","arguments":{}}}' \
  | python3 /home/dev/Hermes/mcp/embed-mcp/server.py
```

## 边界

- 知识库检索仍走 `vault_search.py --rerank`，不改走本 MCP
- 向量建议不可自动套用译文
