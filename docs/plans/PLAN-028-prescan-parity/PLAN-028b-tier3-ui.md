# PLAN-028b 子计划：UI 三段渐进与代际守卫

## 改动

### `scripts/apply-pdf2zh-prescan.py`

- 新增 `_qy_prescan_tier3(files, state)`（普通 `def`，Gradio 线程池执行）
- 挂链：`tier1.then(tier2).then(tier3)`
- 写入 `entry["vector_count"]`、`table_count`、`tier3_done`
- 非 PDF 跳过；异常保留 Tier-2 文案

## 代际守卫

- 入口比对 `generation`
- `scan_pdf_tier3(..., should_abort=lambda: gen != st["_prescan_generation"])`

## 文案示例

- 矢量 12 + 表 19：`检测到 12 处矢量插图，将随文档一并翻译；另有 19 处表格，按文字层翻译。`
- 全 0：`未检测到需要嵌字的插图。`

## 验收

- 上传 PDF 后约 10s 内状态条更新为含矢量/表格的最终文案
- 快速切换文件时 Tier-3 过期结果不覆写 UI
