# PLAN-039e：运行时并表

> 状态：**已完成**
> 父计划：[PLAN-039](./PLAN-039-glossary-governance.md)

## 交付

- `scripts/glossary_merge_runtime.py` → `merged.csv`（仓内 + 同步到 `/home/dev/pdf2zh/glossaries/`）
- sidecar `static_csv` 默认读 merged
- pdf2zh `config.toml` glossaries 指向 merged（保留 auto 可选挂载）
- 保持 `no_auto_extract_glossary=true`

## 验收

- GUI 与 sidecar 对同一 source 同 target
- `verify-plan-039.sh` 含 runtime 断言
