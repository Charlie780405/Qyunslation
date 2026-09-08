# PLAN-028d：Tier-3 预扫描性能恢复与阻塞解除

> 状态：**已合并 main 并部署**
> 日期：2026-09-08
> 父计划：[PLAN-028](./PLAN-028-prescan-parity.md)
> 前置：[PLAN-028c](./PLAN-028c-verify-delivery.md)、[PLAN-030d](../PLAN-030-semantic-layout-translation/PLAN-030d-manifest-ssot-execution-parity.md)

## 目标

恢复 PLAN-028 的 15 秒硬性能门槛，同时保证 19 页金标 PDF 全页完成、Figure/Table/可译图片计数维持 7/3/7，且现代 Tier-3 不再调用 PyMuPDF `page.find_tables()`。

## 根因与决策

- PLAN-030d 接入 Manifest 后，同一页从题注、图片、表格和正文路径重复分析；`figure_table_rects()` 又进入旧 `find_tables()`。
- 19 页样本冷扫描 28.81 秒，在 25 秒 deadline 下仅处理 12 页；14 次 `find_tables()` 占 20.05 秒。
- 扫描器建立私有单页分析上下文，一次读取题注、drawings 和文本块，再将结果传给表格、图片和正文逻辑。
- 旧公开接口继续兼容无预计算参数的调用；现代扫描器显式传递预计算证据和 caption 驱动表格排除区。
- Producer 算法版本由 1.0.0 升至 1.1.0；结构缓存只复用同名同版本条目。
- 版本不匹配时必须删除旧结构缓存。只在读取方忽略过期条目、不删除，截断重扫后执行侧仍会吃到旧算法的完整结果。

## 接口

- `page_caption_profile(page, *, anchors=None)`
- `find_figure_regions(..., *, profile=None, tables=None, drawings=None, text_blocks=None)`
- `labeled_figure_regions(..., *, profile=None, tables=None, drawings=None, text_blocks=None)`
- `translatable_regions(..., *, profile=None, tables=None, drawings=None, text_blocks=None)`
- `find_safe_vector_figures`、`table_regions`、`table_exclusion_rects` 和 `body_blocks` 接受对应的可选预计算输入；旧调用方式不变。
- `ManifestStore.get_current(digest, producer_name=..., producer_version=...)`：预扫描与执行共用。

## 验收

| 项 | 结果 |
|---|---|
| 每页只解析一次题注；现代扫描器不调用 `table_rects/page.find_tables()` | 通过 |
| 三冷一热：中位数 `<12s`、最大值 `<15s`、热缓存 `<1s` | 中位数 1.428s / 最大 1.687s / 热 0.012s |
| 金标 19/19 页、`truncated=false`、计数 7/3/7 | 通过 |
| 过期缓存在截断重扫后不得残留 | 通过 |
| `verify-plan-028.sh` / `029.sh` / `030c.sh` | PASS |
| PLAN-030e | 不在本分支；待恢复分支 `codex/recovery-030e-030f-20260908` |

## 明确不做

- 不把 030e/030f 混入本性能分支
- 不部署、不合并 main（除非用户明确要求）
- 不清理恢复分支工作区
