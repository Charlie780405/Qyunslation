# PLAN-059c：Figure/Table 结构真值与多栏阅读顺序

> 父计划：[PLAN-059](./README.md)
> 状态：已实施（仓内 fixture 通过；真实多格式金标待补）
> 依赖：059a

## 交付

- 统一 PDF、DOCX、PPTX、图片和 poster 的结构扫描输出；题注、编号、绘图区域、文字层表格和 OCR 表格统一进入 Manifest。
- 物理图片资源与语义 Figure 解耦；跨页/重复 occurrence 和续表归并有稳定 ID；无题注区域只能进入匿名候选，不能随意增加编号。
- 页面布局输出 `SINGLE/DOUBLE/MULTI/FREEFORM`、栏边界、阅读顺序和对象归属。

## 验收标准

- [ ] 期刊金标准确输出 Figure 1–5、Table 1–3，最大 Figure 编号 5；不因重复位图或同一 Figure occurrence 多报。
- [ ] 单栏、双栏、多栏、图表混排、跨栏 Figure 和续表均有稳定顺序；不调用错误的旧检测路径造成重复分析。
- [ ] 结构冲突、无法归属和数量不一致均显式阻断/告警，不静默修正。

## 验证、依赖与范围

- 验证：结构金标、Manifest snapshot、单/双/多栏回归、19 页性能回归。
- 依赖：059a。文件：`qyunslation/structure/scan_*.py`、`table_structure.py`、`tests/structure/`。
- 规模：Large，若超过 5 个代码文件拆为扫描、归并两个实现提交。
