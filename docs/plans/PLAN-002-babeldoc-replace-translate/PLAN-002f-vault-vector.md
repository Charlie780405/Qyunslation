# PLAN-002f：翻译 Vault 入库 + 向量检索

## 目标

每次 pdf2zh 翻译完成后，在 PLAN-002e MinIO 归档之外：

1. 写入 Vault `10-Source-Documents/Translations/DT-*.md`
2. 从 mono PDF 提取正文摘录
3. 调用 Hermes `vault_indexer.py --files … --force` 写入 Chroma
4. 可通过 `knowledge.qyunsgen.com` 混合/向量检索

## 依赖

- PLAN-002e watcher 已部署
- Vault SSOT：`/home/dev/Targets/vault`
- Hermes：`rag/vault_indexer.py` + Ollama bge-m3
- qyunsvault-api `:6201`（生产 systemd）

## 配置（archive.env）

见 `scripts/pdf2zh-archive.env.example` 中 `PDF2ZH_VAULT_*` / `HERMES_*`。

## 验收

```bash
bash scripts/deploy-pdf2zh-archive.sh   # 幂等，含 vault 回填
bash scripts/verify-plan-002f.sh
```

| # | 项 | 期望 |
|---|---|---|
| F-V1 | Vault 有 DT-*.md | 烟测 page1 至少 1 条 |
| F-V2 | Chroma 可检索 | `/api/v1/search` 命中 Translations 路径 |
| F-V3 | watcher 每译必走 | 新 out/ 组 → MinIO + Vault + index |

## 说明

- `10-Source-Documents` 在全量 indexer 的 `SKIP_DIRS` 内；翻译笔记用 **`--files` 定向索引**，不改全库策略。
- HPD 仍不接入 pdf2zh 主路径。
