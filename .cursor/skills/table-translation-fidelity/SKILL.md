---
name: table-translation-fidelity
description: >-
  文献/期刊 PDF 表格译文保真全链：区域识别→HPD 逻辑网格→文字层对齐→翻译→字号→QC→落笔。
  触发：表格崩了、串格、列并了、漏译、字号不统一、与原文格式不对应、无线表、三线表、
  期刊表、COLUMN_CLUSTER_DRIFT、HPD 网格、图被当成表、NOT_A_TABLE、GEOMETRY_CENTER_UNSAFE、
  HPD_GRID_MISMATCH、table normalize、.tbltr、.tblnorm、PLAN-048、SK-Q009。
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

### G 禁令

- 运行时 `page.find_tables()`（与 SK-Q003 一致）
- 把 HPD 脚注 OCR 原文写入交付译文
- 对 `geometry_center` 网格落笔
- 实样 PDF/截图入库（用 `QYUNSLATION_PLAN048_SAMPLE`）

## 降级阶梯

1. HPD 网格 + 三闸门过 → 落笔 `.tbltr`
2. `NOT_A_TABLE` → 跳结构，交图片链
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

## 相关文件

- `qyunslation/structure/table_grid_hpd.py`
- `qyunslation/structure/table_structure.py`（`structure_table_ex` / `align_hpd_grid`）
- `qyunslation/structure/table_qc.py`（三闸门 + `assert_grid_source_safe`）
- `qyunslation/structure/tables.py`（`_expand_region_left`）
- `scripts/pdf_table_translate.py` / `scripts/pdf_table_normalize.py`
- 踩坑：`pitfalls.md`
