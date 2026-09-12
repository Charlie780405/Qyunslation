# SK-Q009 踩坑

## 2026-09-12 PLAN-049j / 小数贪心切错 + 七列塌观感

- **现象**：`90.0111`/`20.422`；表头无 IGA/EASI；第二行空；`Q4WS`+`afetyFU`
- **根因**：`split_cells` `\d+(?:\.\d+)?` 把 `90.011.2` 切成 `90.011`+`2`；`n_cols==6` 不强制七槽；pretreat 不拆 `Q4WSafety`
- **修法**：origin 格形态剥 token；pretreat 拆剂量/小数粘连；`n_cols>=6` 强制七槽
- **判据**：浓度/IGA/EASI 三分列；无三位以上小数粘连 token

## 2026-09-12 PLAN-049i / N= 被邻行擦掉 + 强制拆行压邻 + 表2 跳过 + 末列挤没

- **现象**：表1 表头没有 `(N=130)`，DLQI 与瘙痒行叠墨；表2 行距不均；表3 `第52周`/`安全性随访` 不在访视列，浓度与 IGA 数字同一点，EASI 消失
- **根因**：`_is_header_n_eq_row` skip 后药名行 `band=8` 擦到 N= 的 y；`_fit_cell_lines` 无溢出也拆 `value, N=`；HPD `not_a_table` 整表不居中；spatial 把挤在同 x 的末两列收成一格
- **修法**：表头 N= 按格回写；擦除带夹邻行中点；仅格宽不够才拆行；矮窄假表仍对行；丢末列改 `_assign`；七列强制 EASI 槽
- **判据**：三组 `N=` 独立成行；DLQI 单行不侵入邻行；表2 行 y≈原文；表3 七列且 Visit 锁列

## 2026-09-12 PLAN-049h / 表头重叠当错列 + DLQI 被缩字

- **现象**：表3 ADA/nAb 挤在左缘、浓度头与 IGA 叠；`第52周`/`安全性随访` 看起来像两列；`16.0(7.6), N=128` 小于邻行
- **根因**：只改数据行 x，表头仍 BabelDOC 段流；`unify_region_font` 原位锁错 x；字号抄 dest 已压缩值，一格塞 value+N=
- **修法**：表头关键词入 HPD 槽再落格；Visit 角色锁一列；origin 表体字号 + 格内换行
- **判据**：7 个表头各在列中带；Visit 仅一列；DLQI ≥ 邻行 0.85

## 2026-09-12 PLAN-049g / 缺底线 + 字体不统一 + 表3 列未齐

- **现象**：表1 底线右段消失；译文 SourceHan/Univers/china-s/helv 混用、表3 缺字；表3 七列被空隙并掉
- **根因**：BabelDOC 截断横线；混排字体子集不含全部汉字；空隙投影分不开 ADA/nAb/浓度
- **修法**：`restore_rule_lines` 从原文重描；落笔一族 NotoSansSC；列几何 HPD 优先（表1=4 / 表3=7）
- **判据**：底线与原文同宽；HPD 可达时表3 列数=7；表内无 china-s/helv 混排

## 2026-09-12 PLAN-049f / 西文被拉开 + NRS 续行丢

- **现象**：`china-s` 落笔后 `Q 2 W`/`（13.3）`；表1 NRS 的 `N=129` 挤左缘；表3 邻行叠墨、`每4周` 未还原
- **根因**：整格用中文字体画拉丁；`_neq_only` 跳过数据续行；dest `max(y1)` 作基线
- **修法**：`normalize_ascii` + 混排 helv/china-s；数据 `N=` 续行不 skip；基线跟原文行 y；`Q4W` 覆盖 `每4周`
- **判据**：半角括号；NRS 两行三列；Dose=`Q2W`/`Q4W`；邻行不叠

## 2026-09-12 PLAN-049e / 字在列不在

- **现象**：ljae439 最新 mono 文字齐，表1 `37.1 (13.3) 38.9…`、表3 `40阴性 90.0` 全挤在标签列
- **根因**：BabelDOC 先把整行收成一段，从段框左缘流排；047d 门禁挡不住「尚未分开的 paragraph」
- **修法**：原文数据行空隙出列；只 redact 被挪 span 再 `insert_text`；禁止整区擦除。左列左齐，其余列居中
- **判据**：数据 token x 中心落入原文列中带；模块无 `redact_table_region`

## 2026-09-12 PLAN-049 / 结构链比第一次更差

- **现象**：表1 列粘连、表2/3 双标题碎格；不如 9/11 仅 BabelDOC 的第一次译稿
- **根因**：047d 合并同行短数字 → BabelDOC 列塌；`.tbltr` 再整区擦除重画
- **修法**：文献 `literature_leave_babeldoc`；047d `_numeric_cell` 不合并；窄表只调字号
- **判据**：文献宽表不写涂改 `.tbltr`；重译表1/3 列对齐接近第一次

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
