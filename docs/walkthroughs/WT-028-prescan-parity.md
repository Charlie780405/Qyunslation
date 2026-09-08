# WT-028 预扫描口径与 Tier-3 性能恢复记录

## 交付结果

PLAN-028d 将 19 页 Nature 金标 PDF 的冷扫描从 28.81 秒、12/19 页截断，恢复为全 19 页完成。Figure/Table/可译图片计数保持 7/3/7，表格继续按文字层处理，不纳入图片 OCR。

## 根因证据

修复前 cProfile 共 20,888,335 次调用：

| 热点 | 调用 | 累计耗时 |
|---|---:|---:|
| `PdfStructureScanner._body_objects` | 12 | 23.30s |
| `layout.figure_table_rects` | 12 | 22.82s |
| `pdf_figure_crop.table_rects` | 14 | 20.05s |
| `page.find_tables` | 14 | 20.05s |
| `caption_anchors` | 79 | 3.15s |

正文排除区重新调用表格和图片检测，而图片检测在混排页再次调用 `find_tables()`，形成页内 N+1 式重复分析。

## 实现

| 组件 | 变更 |
|---|---|
| `scan_pdf.py` | 私有 `_PageAnalysis` 汇总题注、表格、图片和正文证据；`_body_objects` 与 `_unnumbered_images` 只消费预计算结果 |
| `pdf_figure_crop.py` | Figure/IMAGE 检测接口接受预计算 profile、table、drawing、text blocks |
| `tables.py` / `layout.py` | 表格横线和正文块复用页面原始证据；现代路径不调用 `find_tables()` |
| `manifest_store.py` | 新增 `get_current()`：生产者名/版本不符则删除结构缓存后当未命中 |
| `doc_image_prescan.py` / `apply-pdf2zh-docimg.py` | 预扫描与执行都走 `get_current()`，避免截断重扫后仍消费 1.0.0 结果 |
| `verify-plan-028.sh` | 使用仓库 Python/可配置样本，缺失依赖明确 BLOCKED，并执行三冷一热性能门禁 |

## 性能结果

`bash scripts/verify-plan-028.sh` 在 `/home/dev/qyunslation/.venv/bin/python` 下得到：

| 场景 | 结果 |
|---|---:|
| 冷缓存 1 | 1.687s |
| 冷缓存 2 | 1.409s |
| 冷缓存 3 | 1.428s |
| 冷缓存中位数 / 最大值 | 1.428s / 1.687s |
| 热缓存 | 0.012s |

优化后 cProfile 为 1,340,442 次调用、2.313 秒；`_analyze_page` 对 19 页累计 1.249 秒，旧 `table_rects/page.find_tables` 不再出现在现代扫描热路径。

## 验证清单

- PLAN-028：PASS，19/19 页、`truncated=false`、7/3/7。
- PLAN-030c：PASS，`expected_red=3`；结构套件仅保留 PLAN-030g PPT 图片执行 XFAIL。
- PLAN-029：PASS，期刊表格注入、幻灯 12 区域和执行一致性均通过。
- PLAN-030e：待恢复分支 `codex/recovery-030e-030f-20260908`，不在本性能分支验收。

## 审查结论

五轴审查后唯一阻断项：版本不匹配时旧结构缓存未删除，截断重扫会把 1.0.0 完整结果留给执行侧。已用失败用例钉死并改为 `get_current()`。其余项（兼容旧 helper、门禁 `mktemp`、`QYUNSLATION_VERIFY_PY` 覆盖）不阻断合并。

## 操作约束

- `QYUNSLATION_VERIFY_PY` 可覆盖默认的仓库 `.venv/bin/python`。
- `QYUNSLATION_PLAN028_SAMPLE` 可指定金标文件；`QYUNSLATION_SAMPLE_ROOT` 可指定样本根目录。
- 缺少运行时或金标样本时门禁返回非零 `BLOCKED`，不得以 skip 伪装通过。
