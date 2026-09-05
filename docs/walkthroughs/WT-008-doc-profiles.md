# WT-008：文档类型排版模板与段落级 OCR 保真

**日期：** 2026-09-05  
**状态：** 已实现（页 1；GUI 补丁随 `pdf2zh.service` 重启生效）

## 背景

V5 译文把 `Our preliminary responses … are` / `enclosed.` 切成两块，左页中间只剩「我们对您会议问题的初步回复是」。根因是 HPD 隐形层按行插入，不是泰州 HPD `/parse` 本身。

## 约束

**未改泰州 HPD-MCP。** 只动本仓库 `scripts/hpd_ocr.py` 对 `/parse` 返回块的本地后处理。`HPD_URL` 仍为 `http://100.67.66.123:8120`。

## 变更

| 项 | 说明 |
| --- | --- |
| `scripts/hpd_ocr.py` | `_merge_lines_into_paragraphs`：列聚类 + 句号后仅小写续行 + 独立称呼保护 |
| `scripts/doc_profiles.toml` | letter / literature / regulatory / generic |
| `scripts/doc_profile.py` | detect / apply / 运行时 `line_skip` patch |
| `scripts/apply-pdf2zh-docprofile.py` | GUI 下拉 + 上传推荐 + HPD 传 `aggressive` |
| `scripts/bench-scanned-page1.sh` | 完整性指标；V6 |
| `scripts/pdf2zh.service` | ExecStartPre 追加 docprofile |

## 页 1 验收（V6 · letter）

- OCR 28 行 → 18 段；`enclosed` 与上一句同段，不再在 `are` 处腰斩
- 译文含「初步回复…如下」，不再单独悬挂「…初步回复是」
- Successful 19 / Fallback 1；字号中位 ~11.2pt
- 中文覆盖约 0.71（地址/专名保留英文，低于 V5 的 0.78 密度，属译文风格而非半句丢失）
- 样例：`deliverables/plan-008-profiles/{letter,literature,regulatory}.mono.png`

## 叠字修复（008 当日）

007 的 `ocr-base` 曾把扫描底图铺回译文页以保留 FDA Logo。底图是英文栅格，段落白底盖不全 → 中英叠在一起。已改为：**不铺扫描底图 + 整页白底 + 中文**。Logo 会丢，可读优先。

## 回滚

去掉 `apply-pdf2zh-docprofile.py` 的 ExecStartPre，重启 `pdf2zh.service`；`hpd_ocr.py` 可关 `aggressive` 退回行级插入。
