---
name: literature-paragraph-layout
description: >-
  学术文献段落版式：YOLO 切碎摘要、框外孤字、段间空洞、首行缩进、Lay summary。
  触发：摘要串行、摘要乱套、段落碎片、框外孤字、段间空洞、行间距、首行缩进、
  Lay summary、没左对齐、layout_id、DocLayout-YOLO、PLAN-047d、PLAN-046b。
---

# 文献段落版式（SK-Q006）

## 铁律

1. **YOLO 会把一段摘要切成多框且字号误判**（实录 4.0/8.0/7.6pt）。合并判据禁止用绝对字号差（≤0.3）与纵向邻接单一条件——改用相对差 ≤35% **或** 任一段 <5pt。
2. **同行横向孤字**（如同 y、x 远离主体的 `of`）必须并回同带前段。
3. **中文行数少于英文 → 框底留空洞**。同 `layout_id` 连续段按译文实际行数收缩框高，段间距取中位数重排（实录 25/24/35pt → ~11pt）。
4. **中文首行缩进封顶 2 字宽**，禁止照抄英文缩进值。
5. **找一个渲染正确的同类段作基准参数源**（项目符号段「本研究增加了什么？」），不要凭空调参。

| 症状 | 先查 | 修法 | 判据 |
| --- | --- | --- | --- |
| 摘要串行/目的碎片 | 段落 y/字号几何 | 047d 合并放宽 | 目的段完整成句 |
| 框外孤字 of | x≈540 短段 | 同行横向合并 | 无宽<40 的拉丁孤段 |
| Lay summary 大空洞 | 段 y 差 vs 源 11pt | `_QY_047D_PARA_LAYOUT` | 段间距标准差<3pt |

## 相关文件

- `scripts/apply-pdf2zh-046b-para-merge.py`
- `scripts/apply-pdf2zh-047d-para-layout.py`
- `scripts/doc_profiles.toml`（`[literature]`）
