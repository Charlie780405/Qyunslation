# WT-006 审核整治

**日期：** 2026-09-05  
**状态：** 已部署  
**git：** `49de3b0`（含 merge PLAN-006 + 前端 static 重建）

## 变更

| 项 | 内容 |
| --- | --- |
| 包名 | 彻底 `docutranslate`→`qyunslation`；无 symlink 依赖 |
| 启动 | import app ~12s→~2.2s（Docling 延迟加载） |
| 模型 | 维持泰州 `qwen3.6:35b-a3b`；`TIMEOUT=300`；`CHUNK_SIZE=8000` |
| 并发 | `.env` 推荐 8；`office.env` 现网仍为 4 |
| 安全 | TLS 默认校验、可选 API Token、Zip Slip/XSS、CORS、MCP 白名单 |
| 缺陷 | extensions 导入修复、`to_thread`、任务 TTL、cacher 锁 |
| unit | `qyunslation-office.service` → `127.0.0.1:8010` |

## 验收

- `bash scripts/verify-plan-006.sh` 全绿
- `curl 127.0.0.1:8010/service/meta` → version
- `curl 127.0.0.1:8010/service/glossary` → 200

## 回滚

`git checkout 4d53da3 && systemctl --user restart qyunslation-office`（需临时恢复 `docutranslate` symlink）。
