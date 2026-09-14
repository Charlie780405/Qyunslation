# PLAN-059a：12 项问题基线、结构/API/QA 契约

> 父计划：[PLAN-059](./README.md)  
> 状态：待批准

## 交付

- 用用户提供的 PDF、监管表单、双栏文献和图片证据建立匿名复现记录，逐项标注页面、对象 ID、源/译 bbox 和错误类型。
- 定义 `physical_image_count`、`semantic_figure_count`、`table_count`、`occurrence_count`、`unresolved_count` 及 Figure/Table 编号规则。
- 固化 `PRESERVE`、`TRANSLATE`、`OCR_TRANSLATE`、`TABLE_TRANSLATE`、`FOOTNOTE_TRANSLATE` 对象策略和错误码。
- 固化模型 trace、源文件 hash、DPI、字号、粗体、栏位、行数和版式 QA 字段。

## 验收标准

- [ ] 12 项错误均有可重复 fixture 或真实样本定位；不可提供的样本标记 BLOCKED，不用假数据冒充通过。
- [ ] API/Manifest schema 能区分物理资源、语义对象和出现位置。
- [ ] 参考文献整体保留、缩写脚注、原文 hash 和模型 trace 均有机器可检验字段。

## 验证、依赖与范围

- 验证：schema 测试、Manifest contract 测试、错误码静态检查。
- 依赖：无。文件：`qyunslation/structure/models.py`、`manifest_store.py`、`tests/structure/`、`docs/contracts/`。
- 规模：Medium。
