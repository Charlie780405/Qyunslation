# SK-Q009 踩坑

## 2026-09-12 PLAN-048 / ljae439（BJD/OUP 三线表）

### `_merge_column_clusters` 把真列并掉

- **现象**：表3 `阴性 阴性`、`204010`、空行；nAb 列并进浓度列
- **根因**：raw 列簇 `[231.0, 246.7, 262.0, 273.7, 287.9]` 被 `thr=max(small)*1.15≈18` 并成 `260.3`。格内间隙 10.4pt 与列间间隙 15.7pt 不可用单一全局阈值区分
- **修法**：删除合并路径；HPD 出列；空隙投影回退；`geometry_center` 不落笔
- **判据**：表3 nAb 与浓度分列

### 047e 放宽闸门让坏结构过闸

- **现象**：日志仅 `table:1 COLUMN_CLUSTER_DRIFT`；表2/3 写出 `.tbltr` 且乱
- **根因**：`fragments>=2 and sparse` 放宽后，坏网格仍过 `assert_table_qc_clean`
- **修法**：`assert_grid_source_safe`；坏源不画；失败走 normalize
- **判据**：`geometry_center` 不得 TRANSLATED

### 表2 是图不是表

- **现象**：图2 预测因子标签被涂改（`% 识别别`）
- **根因**：`caption_rules` 区域 6 个单元全是图注，0 空隙
- **修法**：HPD 不吐 `<table>` → `NOT_A_TABLE` → 交图片链
- **判据**：该区无结构链落笔

### 表3 缺 Dose 列 → 双渲染器

- **现象**：左列 Q2W 英文（BabelDOC），右侧中文（我们）
- **根因**：横线群 bbox 左边界切掉 Dose；HPD 裁剪也看不到
- **修法**：`_expand_region_left` 纳入同行带左墨迹
- **判据**：区域含 Dose/Q2W 或左边界扩展

### HPD 文本不能进译文

- **现象**：脚注 `neutralizing studies`、`O2W`、`RA 1 and 2`
- **根因**：视觉 OCR 错字
- **修法**：HPD 只供行列对齐；`source_text` 一律文字层
- **判据**：`cross_check` 数字护栏；译文无上述错词

### 宽表头桥接空隙

- **现象**：全表投影空隙少一列
- **根因**：表头跨列墨迹填满 gutter
- **修法**：只用数据行做空隙投影
- **判据**：表1 数据行 → 4 列

### HPD OCR：O2W ↔ Q2W

- **现象**：Dose 列空，文字层有 `Q2W` 但 HPD 格是 `O2W`
- **修法**：短 token 1 编辑距离 + 行相似度 OCR 折叠
- **判据**：数据行 c0=`Q2W`/`Q4W`

### 几何折行未并进 HPD 行 → 表头/`N=` 切碎后落笔更乱

- **现象**：表1 `( N = 130) ( N =` / `134) ( N =`；表3 `concentration (` / `a nAb`；整区擦后再画碎片
- **根因**：HPD 已把 `Tralokinumab Q2W (N=130)`、表头上下两行并成一格；`align_hpd_grid` 只配对单行几何，残留 `N=` 按 x 塞错列
- **修法**：对齐前 `_merge_geo_wrap_lines`（N= 续行 / 逗号折行 / 合并后更像 HPD 的表头）；格内禁止展开 `Q2W`；`literature_paint_safe` 只拦切碎格与重叠，不拦完整 `(N=130)`
- **判据**：表1 列含药名+N=；表3 表头含 Dose/nAb/concentration；`.tbltr` 不再双渲染碎片

## Hermes 同源坑（对照）

- `literature-knowledge-base/pitfalls.md`：52 号 OUP/BJD `find_tables=0`；108/109/112「10 列收成 6 列」
- 解法同源：HPD + `cross_check` / `looks_collapsed` / `coverage_ok`
