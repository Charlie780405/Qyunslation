---
name: table-translation-fidelity
description: >-
  文献/期刊 PDF 表格译文保真全链：区域识别→HPD 逻辑网格→文字层对齐→翻译→字号→QC→落笔。
  触发：表格崩了、串格、列并了、漏译、字号不统一、与原文格式不对应、无线表、三线表、
  期刊表、COLUMN_CLUSTER_DRIFT、HPD 网格、图被当成表、NOT_A_TABLE、GEOMETRY_CENTER_UNSAFE、
  HPD_GRID_MISMATCH、table normalize、.tbltr、.tblnorm、PLAN-048、PLAN-049、PLAN-049e、PLAN-049f、
  LITERATURE_LEAVE_BABELDOC、交还 BabelDOC、列内居中、居中对齐、数值贴左、全角括号、
  字母被拉开、遮盖、串行、NRS 拆行、缺底线、字体不统一、字体缺失、HPD 补全、
  PLAN-049g、PLAN-049h、PLAN-049i、PLAN-049j、表头重叠、字偏小、N=130、行距不等、丢末列、EASI、粘连、90.0111、
  剂量重复、表头没分开、伴ADA访视的EASI、Visit with ADA、折行表头、
  第一列格线、格线不贯穿、表2格线不完整、SK-Q009。
---

# 表格类翻译保真（SK-Q009）

表格链总纲。监管表单特殊规则见 [SK-Q003](../pdf-regulatory-form-fidelity/SKILL.md)；本 skill 覆盖期刊三线表/无线表与 Hermes HPD 网格路径。

## 施工顺序

1. 确认 `grid_source`（manifest `detector_evidence.details`）
2. 查 QC：`NOT_A_TABLE` / `GEOMETRY_CENTER_UNSAFE` / `HPD_GRID_MISMATCH` / `COLUMN_CLUSTER_DRIFT`
3. HPD 可达？`curl $QYUNSLATION_HPD_BASE_URL/health`；缓存 `~/.cache/qyunslation/hpd-grid/`
4. 结构失败 → 是否走了 `pdf_table_normalize`（`.tblnorm`）而非硬画坏网格
5. 部署：`bash scripts/deploy-translate-stack.sh`

## 通用原则

- **HPD 出结构，文字层出内容**——HPD OCR 文本禁止写入译文（实证：`neutralizing studies`/`O2W`/`ECZTRA`）
- **放宽闸门而不修结构 = 把垃圾画上去**（047e 回归原文）
- **跳过 ≠ 保留原文**——BabelDOC 先于我们落笔，实测表区可有 9 种字号（最小 4.65pt）

## 铁律

### A 结构来源

| 项 | 内容 |
| --- | --- |
| 症状 | 串格、列并了、`阴性 阴性`、`204010` |
| 先查 | `grid_source`；是否仍走 `geometry_center` |
| 修法 | HPD 优先 → 数据行空隙投影 → `geometry_center` **一律不落笔** |
| 判据 | 表1=4 列、表3≥6/7 列且 nAb≠浓度；无中心聚类合并 |

### B 闸门

| 项 | 内容 |
| --- | --- |
| 症状 | 表格又崩了但日志无 HARD |
| 先查 | 047e 是否把 `fragments AND sparse` 放宽后坏结构过闸 |
| 修法 | `assert_grid_source_safe`；`cross_check`/`looks_collapsed`/`coverage_ok` |
| 判据 | `geometry_center` 不得出现 `.tbltr` 落笔 |

### C 假阳性

| 项 | 内容 |
| --- | --- |
| 症状 | 图上的标签被译成乱表 |
| 先查 | HPD 是否吐 `<table>`；区域单元是否全是图注 |
| 修法 | `NOT_A_TABLE` → 跳结构链，交图片链（SK-Q002） |
| 判据 | 该区无 `.tbltr` 涂改 |

### D 区域边界

| 项 | 内容 |
| --- | --- |
| 症状 | 左列英文、右列中文（双渲染器同表） |
| 先查 | `table_regions` bbox 是否切掉 Dose/Q2W |
| 修法 | `_expand_region_left` 纳入同行带左墨迹 |
| 判据 | 表3 含 Dose 列或左边界扩到该列 |

### E 内容来源

| 项 | 内容 |
| --- | --- |
| 症状 | 译文里出现 HPD OCR 错字 |
| 先查 | 是否把 HPD cell 文本当 `source_text` |
| 修法 | 只对齐用 `normalize_for_align`；`compose_cell_text` 取文字层 |
| 判据 | 源文本与 PDF `get_text` 一致 |

### F 跳过 ≠ 保留原文

| 项 | 内容 |
| --- | --- |
| 症状 | 「跳过表格」后字号仍乱 |
| 先查 | BabelDOC 已渲染的表区字号种类 |
| 修法 | 失败走 `pdf_table_normalize` 角色分带 p75 + 漏译补翻 |
| 判据 | 表体字号种类 ≤3；拉丁漏译率下降 |

### H 列内居中（049e）

| 项 | 内容 |
| --- | --- |
| 症状 | 字都在，数值贴左列（`40阴性 90.0` / `37.1 38.9 38.3` 连排） |
| 先查 | 原文同行数字是否已在分列 x 带；译文是否整行一段 |
| 修法 | HPD **格**落笔（含表头关键词入槽）；数据 Visit 锁一列；禁止表头原位 restyle |
| 判据 | 表3 表头 7 槽各在列中带；`第N周`/`安全性随访` 同 Visit 列；浓度中心 ≠ IGA 中心 |

### I 表内西文半角 + 一族字体（049f/g）

| 项 | 内容 |
| --- | --- |
| 症状 | `Q 2 W` / `（13.3）` / SourceHan+Univers+helv 混用 / 表3 缺字方框 |
| 先查 | 落笔是否 `qy-tbl`（NotoSansSC）；有无 `normalize_ascii` |
| 修法 | 全角折半角；整格 NotoSansSC（含半角拉丁）；origin `Q4W` 覆盖 dest `每4周` |
| 判据 | 表内无全角括号；无 china-s/helv 混排；无缺字 |

### K 表头 N= / 拆行 / 小表对行（049i）

| 项 | 内容 |
| --- | --- |
| 症状 | 表1 丢掉 `(N=130)`；DLQI 的 `N=` 压到下一行；表2 行距乱；表3 访视错列、浓度与 IGA 挤一点、丢 EASI |
| 先查 | 表头 N= 是否被 skip；上一行 `band=8` 是否吃到 N= 的 y；`_fit_cell_lines` 是否无溢出也拆行；`not_a_table` 是否整表跳过居中；spatial 末列是否空 |
| 修法 | 表头 `N=` 按格回写 `(N=130)`；擦除带夹邻行中点；仅格宽不够才拆行；矮窄 `not_a_table`（表2）仍按原文行 y 居中；七列强制 EASI 槽，spatial 丢末列则改 `_assign`；HPD 反转列丢掉；dest 行少则按 origin 顺序舀段流 |
| 判据 | 表1 y≈108 有三组 `N=`；DLQI 不侵入瘙痒行；表2 行 y 跟原文（容差 2pt）；表3 `第52周`/`安全性随访` 与「访视」同列；末列表头=`伴ADA访视的EASI` |

### L 粘连切分 / 七列收口（049j）

| 项 | 内容 |
| --- | --- |
| 症状 | `90.0111`/`20.422`；表头无 IGA/EASI；第二行只剩 `Q2W`；`Q4WS`+`afetyFU` |
| 先查 | `split_cells` 是否把 `90.011.2` 切成 `90.011`+`2`；`header_slots_from_blob(n=6)`；pretreat 是否拆 `Q4WSafety` |
| 修法 | 按 origin 格形态（int/dec1/dec2）剥 token；pretreat 拆剂量粘连与小数粘连；`n_cols>=6` 强制七槽；空行从 blob 补 |
| 判据 | 首行浓度=`90.0`、IGA=`1`、EASI=`11.2`；无三位以上小数粘连；七表头各在列中带 |

### M 折行表头只落一次（数据已分列、表头仍糊）

| 项 | 内容 |
| --- | --- |
| 症状 | 表3 **数据已分开**，但表头仍粘：`剂量` 出现两列；第 2 列不是「访视」；末列不是「伴ADA访视的EASI」而是「访视时 EASI」或缺头 |
| 先查 | origin 表头是否两行（`IGA at visit` / `EASI at visit` 上行，`Dose` / `Visit with ADA` / `with ADA` 下行）；是否对**每一行**各写一遍 `header_slots`；`_header_skip_cell("with ADA")` 是否让访视列空着、BabelDOC 残留「剂量」 |
| 修法 | `merge_origin_header_cells` 并折行再 `header_texts_from_merged` **每槽只写一次**；规范七槽=`剂量/访视/ADA/nAb/曲罗芦单抗浓度/伴ADA访视的IGA/伴ADA访视的EASI`；折行残片不入槽；「剂量」禁止出现在槽 0 以外 |
| 判据 | `texts.count("剂量")==1`；`texts[1]==访视`；`texts[6]==伴ADA访视的EASI`；表头 jobs 只有 1 条 |

### J 三线从原文补（049g）

| 项 | 内容 |
| --- | --- |
| 症状 | 表1 缺底线 / 底线右段被截；**第一列格线不贯穿**；表2 右栏（% 列）无线 |
| 先查 | 原文 raw 分段：表3 左段约 26pt（Dose）、表2 右段约 52pt；`_horizontal_lines` 是否**先按页宽 10% 丢掉短段再合并** |
| 修法 | 短段先收（≥8pt）再按 y 合并，**合并后**才用页宽阈值；`table_rule_lines` **不按 bbox 截 x**；`restore_rule_lines` 重描完整 x；擦字白块之后再画线 |
| 判据 | 表3 横线 x0≤68（穿过剂量/Q2W）；表2 横线 x1≥280（含 % 列）；底线与原文同宽（容差 4pt） |

### G 禁令

- 运行时 `page.find_tables()`（与 SK-Q003 一致）
- 把 HPD 脚注 OCR 原文写入交付译文
- 对 `geometry_center` 网格落笔
- 文献整区 `redact_table_region` + `paint_fitted_blocks`
- 实样 PDF/截图入库（用 `QYUNSLATION_PLAN048_SAMPLE`）

## 降级阶梯

0. **文献（RESEARCH/REVIEW）默认不整区落笔**（PLAN-049）——BabelDOC 段流保留；窄矮表仅字号归一；**049e 只按列挪位**；**049f 西文半角 + 原文行 y**；**049g HPD 列 + Noto + 三线**；**049h 表头按格写、格内换行不缩字**；**049i 表头 N= 回写、仅溢出拆行、矮窄 not_a_table 仍对行、七列强制 EASI**；**049j origin 形态剥 token、粘连切分**；**折行表头并格后每槽只写一次（规范末列=伴ADA访视的EASI）**
1. 监管表单：HPD 网格 + 三闸门过 → 落笔 `.tbltr`
2. `NOT_A_TABLE` → 大图交图片链；**表2 量级矮窄框仍列居中对行**（049i）
3. 闸门未过 / `geometry_center` → 不落笔，字号归一
4. HPD 不可达 → 空隙投影；列数可疑 → 退 3
5. 全失败 → 只字号归一 `.tblnorm`

## 环境变量

| 变量 | 含义 |
| --- | --- |
| `QYUNSLATION_HPD_GRID` | `hpd`（默认）/`gutter`/`off` |
| `QYUNSLATION_HPD_BASE_URL` | 默认 `http://100.67.66.123:8120` |
| `QYUNSLATION_HPD_GRID_CACHE` | 缓存目录 |
| `QYUNSLATION_PLAN048_SAMPLE` | 实样 PDF 路径（verify 可选） |
| `QYUNSLATION_FONT` | 表内一族字体，默认 `NotoSansSC-Regular.otf` |

## 相关文件

- `qyunslation/structure/table_grid_hpd.py`
- `qyunslation/structure/table_structure.py`（`structure_table_ex` / `align_hpd_grid`）
- `qyunslation/structure/table_qc.py`（三闸门 + `assert_grid_source_safe`）
- `qyunslation/structure/tables.py`（`_expand_region_left`）
- `scripts/pdf_table_translate.py` / `scripts/pdf_table_normalize.py` / `scripts/pdf_table_column_center.py`
- 踩坑：`pitfalls.md`
