# PLAN-028 预扫描口径对齐：矢量插图纳入与表格独立计数

## 一、背景与目标

PLAN-027b 预扫描 Tier-1 仅统计 PDF 嵌入位图（`page.get_image_info`）。Nature 等学术 PDF 的多面板折线图、机制图多为 **矢量路径**，翻译执行阶段由 `pdf_image_translate.py` 的 `find_safe_vector_figures` 裁切 OCR 嵌字，但上传预扫描仍报「检测到 0 处候选插图」，违反 PLAN-027 不变量 4「预扫描与执行结论幂等对齐」。

本纲领目标：**新增 Tier-3 结构扫描，将矢量插图纳入预扫描计数；表格作为独立一类仅计数上报（按文字层翻译），不改变翻译行为。**

---

## 二、子计划矩阵

| 编号 | 名称 | 核心职责 | 关键产物 | 前置 |
|---|---|---|---|---|
| **028a** | 结构扫描内核与表格共享 | `table_rects` 公开、`find_safe_vector_figures(tables=)`、`scan_pdf_tier3` | `pdf_figure_crop.py`<br>`doc_image_prescan.py` | PLAN-027d |
| **028b** | UI 三段渐进与代际守卫 | `_qy_prescan_tier3` 挂链、逐页 `should_abort` | `apply-pdf2zh-prescan.py` | 028a |
| **028c** | 验证与交付 | `verify-plan-028.sh`、WT-028 | 脚本 + 文档 | 028a, 028b |

```mermaid
flowchart LR
    T1[Tier-1 位图 0.2s] --> T2[Tier-2 OCR 探针 1-3s]
    T2 --> T3[Tier-3 矢量+表格 约9s]
    T3 --> UI[最终 summary_text]
```

---

## 三、性能基线（19 页论文 PDF）

| 步骤 | 耗时 | 层级 |
|---|---|---|
| `get_image_info` | 0.21s | Tier-1 |
| `find_tables` + `find_safe_vector_figures`（共享 tables） | 7.9s | Tier-3 |
| 朴素串行（不共享） | 21s | 禁止 |

---

## 四、质量不变量

1. **口径对齐**：Tier-3 矢量计数与 `pdf_image_translate` 使用同一 `find_safe_vector_figures` 门禁。
2. **表格仅上报**：文案固定「按文字层翻译」，不纳入插图 OCR。
3. **代际守卫**：Tier-3 入口与逐页 `should_abort` 比对 `_prescan_generation`。
4. **Fail-Soft**：Tier-3 异常保留 Tier-2 文案，不阻断翻译。

---

## 五、明确不做

- 表格 OCR 嵌字（与文字层重复）
- Tier-3 结果缓存到翻译阶段
- 修改位图几何门槛（小 logo 仍过滤）
