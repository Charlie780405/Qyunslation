# PLAN-027d 子计划：PDF 双策略与安全原位贴片

## 一、目标与解决痛点

1. **解决痛点 1（PDF 共享 XObject 全局污染）**：
   - 审查指出的严重陷阱：直接调用 `page.replace_image(xref)` 是全文档全局替换。如果某张图同时被用于封面、正文或目录，会导致未经校验的全局覆盖。
2. **解决痛点 2（Hermes 抽图退化整页灾难）**：
   - Hermes 文献入库算法在矢量区域难以分离时会退回截取整页（`page.rect`）。若直接套用在文档翻译中，会将整页正文、表格、页码全部强行压成 200 DPI 位图，使矢量文字层彻底丢失。
3. **解决痛点 3（带软蒙版 `/SMask` 透明图错位）**：
   - PDF 常见透明图带有单独的 `/SMask` 流，若替换图尺寸稍有拉伸，蒙版就会与彩色像素错位，边缘泛白发虚。

---

## 二、详细技术实现架构

```
[PDF 页面对象解析]
        │
        ├─► 收集 (page_no, xref, bbox, ctm, smask_xref) 实例表
        │
   ┌────┴────────────────────────┐
   ▼                             ▼
【策略 A：独立位图 XObject】    【策略 B：安全矢量图聚类】
   │                             │
   ├─ 检查 xref 引用计数         ├─ 聚类 drawings 与短文本标签
   │  (多引用则克隆局部 XObject)  ├─ 边界门禁: 重叠正文>10%或面积>80%立即拒绝!
   ├─ 严格像素尺寸断言           ├─ 200 DPI 区域栅格化
   ├─ sidecar 嵌字翻译           ├─ sidecar 嵌字翻译
   └─ page.replace_image 无损换  └─ page.insert_image 原位覆盖
```

---

### 1. 策略 A：位图 XObject 实例解耦与无损替换

在 `scripts/pdf_image_translate.py` 中实现：

1. **多引用隔离（XObject Isolation）**：
   - 扫描全文档所有页面的资源字典；
   - 若某 xref 仅在当前设计图出现一次，允许直接调用 `page.replace_image(xref, stream=new_bytes)`；
   - 若该 xref 在多处复用：
     - 在 PDF 中通过 PyMuPDF 底层底层流操作克隆一个新的 XObject 编号 `xref_new`；
     - 仅重写该页面 `/Resources /XObject` 字典中对应名称的引用，指向 `xref_new`；
     - 隔离后执行局部替换，其余页面的引用完全不受影响。
2. **严格像素与蒙版对齐**：
   - 译后图片像素宽高必须与原图像素尺寸 **100% 绝对一致**；
   - 若存在 `/SMask`，保持透明蒙版通道无位移。

---

### 2. 策略 B：去危险回退的安全矢量图聚类（`scripts/pdf_figure_crop.py`）

为防止将普通表格、段落框误判为流程图，设定**三道强门禁**（Fail-Closed 闭环保护）：

```python
def find_safe_vector_figures(page, exclude_rects) -> list[fitz.Rect]:
    """
    定位 PDF 页面内的矢量流程图/设计图，且 100% 保证不损伤正文文字层。
    """
```

**三道门禁判定**：
1. **面积安全门禁**：聚类矩形面积若超过页面总面积的 80%，**严格禁止退回整页，直接判定为不可处理并放弃**。
2. **正文文字防触碰门禁**：计算候选区域与页面内长段落文字块（字符数 > 60 的正文段落）的交集面积：
   - 若重叠率 > 10%，判定为正文穿插混排，**立即拒绝整块覆盖**，防止文字被栅格化抹杀。
3. **表格线防误伤门禁**：通过 `page.find_tables()` 探测结构化表格线，若候选框与表格区域相交，直接剔除。

**回嵌执行**：
- 仅对通过全部门禁的纯净矢量设计图执行 `page.get_pixmap(clip=rect, dpi=200)`；
- 经 sidecar 嵌字后，使用 `page.insert_image(rect, stream=data, overlay=True, keep_proportion=True)` 覆盖回嵌。

---

### 3. Gradio 集成与扫描件防重入保护（`scripts/apply-pdf2zh-docimg.py`）

在 `gui.py` 的 `_run_translation_task` 中注入补丁：

```python
# _qy_imgtr: PDF 内嵌插图翻译前置处理
_file_hash = _qy_get_file_sha256(file_path)
if not state.get("_hpd_retried") and not state.get("_imgtr_done", {}).get(_file_hash):
    from pdf_image_translate import translate_pdf_images
    
    # 记录原始原稿路径，供 HPD fallback 使用
    state["_pre_imgtr_origin_path"] = str(file_path)
    
    def _pdf_img_cb(cur, total):
        progress(0.08 + 0.12 * cur / max(total, 1), desc=f"文档插图翻译 ({cur}/{total})")
        
    imgtr_pdf_path = translate_pdf_images(file_path, to_lang=to_lang, progress_cb=_pdf_img_cb)
    if imgtr_pdf_path and imgtr_pdf_path.is_file():
        file_path = imgtr_pdf_path
        state.setdefault("_imgtr_done", {})[_file_hash] = True
```

**HPD 降级保护**：
- 若后续 BabelDOC 抛出 `Scanned PDF` 异常，必须将 `file_path` 还原为 `_pre_imgtr_origin_path`（原始未处理 PDF），再送入 HPD，绝对防止已翻好的文字图被二次 OCR 搞乱。

---

## 三、验收标准

1. **共享 XObject 隔离验收**：
   - 构造一个 2 页 PDF，第 1 页页眉 Logo 与第 2 页正文大图复用同一个 xref；翻译后，第 2 页图内文字中英互译成功，第 1 页 Logo 像素和色彩 100% 无变化。
2. **正文防覆盖防线验收**：
   - 构造一个含正文段落与下方流程图的页面；流程图被翻译覆盖，而上方正文文字依然保留矢量文字层（可以鼠标高亮选中、可以复制出文字）。
3. **带旋转页对齐验收**：
   - 横向页面（旋转 90 度）的设计图，回填位置分毫不差，不出现 90 度倒置或偏移到页面外。
