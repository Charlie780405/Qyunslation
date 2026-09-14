# PLAN-051a：金标整本执行器

> 状态：**已实现**
> 父计划：[PLAN-051](./PLAN-051-gold-pharma-mqm.md)
> 验收：`pytest tests/gold/test_plan051a_run.py`；`scripts/plan051-run-gold.py --dry-run`

## 目标

对 catalog 真件走与生产相同的 CLI，按源 `sha256` 缓存，写出可被 051b 消费的 `run-manifest.json`。

## CLI（复用 033n）

```bash
pdf2zh_next --config-file <tmp-config> --disable-config-auto-save \
  --ollama --ollama-model qwen3.6:35b-a3b \
  --ollama-host "$QYUNSLATION_OLLAMA_HOST" \
  --lang-in en --lang-out zh --output "$OUT" \
  --ignore-cache --no-auto-extract-glossary \
  --watermark-output-mode no_watermark \
  "$SRC_PDF"
```

后处理（imgtr / tbltr）与 [scripts/rerun-plan033-head-evidence.sh](../../../scripts/rerun-plan033-head-evidence.sh) 同链；缺 sidecar → BLOCKED（exit 2）。

## 交付

| 路径 | 说明 |
| --- | --- |
| `qyunslation/gold/plan051_run.py` | 选条目、缓存、调 CLI、写 manifest |
| `scripts/plan051-run-gold.py` | CLI 入口 |
| `tests/gold/test_plan051a_run.py` | mock CLI，不烧 GPU |

## 缓存

目录：`$QYUNSLATION_PLAN051_OUT/$entry_id/$sha25612/`（默认 `/tmp/plan051-out`）。

命中：`run-manifest.json` 存在且 `source_sha256` 一致、`mono` 文件存在 → 跳过翻译。

`run-manifest.json` 键：`entry_id`, `source_sha256`, `git_head`, `model_id`, `mono`, `dual`, `sidecar`, `exit_code`, `cached`。

标志：`--dry-run` / `--limit N` / `--entry ID` / `--include-synthetic`。

## 判据

- 假 CLI：首次写缓存，第二次不调用 CLI；源哈希变了重跑。
- 缺 GOLD_ROOT / 真件 / CLI：exit 2，不伪造 mono。
- 不改 `catalog.json` 二进制；不入库产物。

## Out of Scope

- 不算 MQM 分（→ 051b）
- 默认不跑合成件
- 不改 pdf2zh 补丁
