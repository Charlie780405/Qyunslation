# WT-032：归档卫生（文件名清洗与编号收口）

## 一、实现概要

1. **共用清洗模块**：新增 [`filenames.py`](../../qyunslation/archive/filenames.py) — `strip_pipeline_markers()` 只从 stem 尾部反复剥离已知标记（`.no_watermark[.lang]`、`.hpd-ocr`、`.imgtr`、`.letter-mono`、`.mono`/`.dual`、`_translated`、尾部语言码）到稳定为止，幂等；未知后缀保留。
2. **pdf2zh 侧**：`normalize_group_stem()` 委托该模块（补 `.imgtr`）；`infer_original_filename()` 入口再规范化一次，对未规范化入参不再产出脏名。
3. **office 侧**：`office-archive-watch.py` 原本 `original_filename=path.name` 直接写译文产物名，改为 `original_filename_from_product()` 还原上传名。
4. **编号前缀**：`index_db.py` 新增 `ARCHIVE_ID_PREFIX = "QY"` 与 `is_archive_id()`；历史 `DT-` 不迁移，两种前缀都认。计数器按年递增、与前缀无关，不会重用编号。
5. **存量修正**：[`fix-archive-filenames.py`](../../scripts/fix-archive-filenames.py) 默认 dry-run，`--apply` 前自动备份 `index.db`。

## 二、验证

```bash
bash scripts/verify-plan-032.sh
```

六项全 PASS，其中最后一项断言**全量套件 0 failed**。

## 三、立项判断的实测修正

立项时把三个红灯全部判为实现缺陷，实测后修正：

| 项 | 立项判断 | 实测 |
| --- | --- | --- |
| `output_group_key` 保留 `.no_watermark.zh` | 实现缺陷 | **测试过期**，实现早已剥离，返回 `page1` |
| `infer_original_filename` | 主缺陷 | 次要，仅对未规范化入参不设防 |
| `.imgtr` 未剥 | 未发现 | 真缺口 |
| office 侧写产物名 | **未发现** | **主缺陷**，生产库污染的主要来源 |

## 四、生产存量

对 `/home/dev/pdf2zh/archive/index.db` 跑 dry-run：27 条记录中 **10 条**带流水线标记。

| 样例 | 修正后 |
| --- | --- |
| `FDA responses on PIND.hpd-ocr.zh-CN.pdf` | `FDA responses on PIND.pdf` |
| `41467_2024_Article_53384.imgtr.pdf` | `41467_2024_Article_53384.pdf` |
| `方案设计图-20260728.zh.jpg` | `方案设计图-20260728.jpg` |
| `QX027N-201-CSP-V1.3 20260803_translated.docx` | `QX027N-201-CSP-V1.3 20260803.docx` |

`plan019-zh_translated.docx` → `plan019-zh.docx`：`-zh` 是原文件名的一部分（连字符而非点），未被误剥。

**存量写入需人工确认后执行**，本 WT 记录时尚未 `--apply`。

## 五、影响面核实

- Vault 笔记名为 `{archive_id}-{stem}.md`，新笔记将是 `QY-2026-*`；旧 `DT-` 笔记不动。
- Hermes `rag/vault_indexer.py` 按目录索引，无 `DT-` 前缀过滤，改动不影响向量检索。
- `verify-plan-002f.sh` 的笔记存在性断言放宽为 `QY-`/`DT-` 兼容；`verify-plan-013.sh` 断言的是 `DT-2026-0016` 这条历史记录，保留不动。

## 六、非目标

- 归档存储后端与索引 schema 变更
- 历史 `DT-` 记录的编号迁移
- Vault 导出链路与 Hermes 跨仓依赖（PLAN-030i）
