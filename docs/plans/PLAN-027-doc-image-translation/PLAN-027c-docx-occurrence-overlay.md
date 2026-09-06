# PLAN-027c 子计划：DOCX DrawingML 实例解耦与嵌字回填

## 一、目标与解决痛点

1. **解决痛点 1（页眉页脚与隔离容器漏处理）**：
   - 之前只扫 `doc.part.rels`，导致页眉、页脚、脚注、尾注中的图片完全遗漏。
2. **解决痛点 2（共享 ImagePart 交叉污染）**：
   - 同一个图片资源如果在页眉作为小 Logo，在正文又作为大图引用，直接修改 `part._blob` 会导致两处被同时修改，严重破坏排版。
3. **解决痛点 3（脱离物理显示尺寸盲目翻译）**：
   - 之前直接按原始像素判断，无法得知图片在 Word 页面上实际被缩放到了多大（EMU 物理宽高），易把缩小的图标送翻或把拉伸的大图漏掉。
4. **解决痛点 4（串行无进度与黑盒错误）**：
   - 原处理为同步串行阻塞，多图时用户界面无进度反馈，且无任何 manifest 结果审计。

---

## 二、详细技术实现方案

### 1. DrawingML DOM 深度遍历与物理尺寸解析

遍历 Word 全部 Story 容器（Body、Section Headers、Footers、Footnotes），通过 XPath 定位所有 DrawingML 节点：

```python
# 命名空间映射
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
}
```

每个 Drawing 节点提取以下物理元数据：
- `embed_rid = blip.get(f"{{{NS['r']}}}embed")`（关系 ID）
- 物理尺寸：读取 `<wp:extent cx="..." cy="...">`
  - 换算公式：`width_pt = cx / 12700`, `height_pt = cy / 12700`（1 磅 = 12700 EMU）
- 裁剪属性：读取 `<a:srcRect l="..." t="..." r="..." b="...">`
- 所在区域标签：`is_header = True` 若来自 `HeaderPart`

---

### 2. 实例级解耦与 ImagePart 克隆（Decoupling & Cloning）

当且仅当一个图片符合翻译策略时，检查其引用度（Occurrence Count）：
- **单处引用**：直接原位替换对应 `ImagePart._blob`，内存开销最小；
- **多处引用（例如正文与页眉共用，或不同裁剪区域）**：
  1. 调用 `target_part.package.part_related_by` 机制；
  2. 新建独立的 `ImagePart`，写入翻译后的新 bytes；
  3. 在当前容器的 `.rels` 中生成新的 `rId_new` 关联到新 Part；
  4. 仅将当前被翻译的 `<a:blip>` 的 `r:embed` 属性重写为 `rId_new`。
  
> **成效**：彻底解耦页眉 Logo 与正文设计图，互不干扰，零副作用。

---

### 3. 并发翻译与平滑进度透传

利用 `ThreadPoolExecutor` 对各有效候选图执行并发嵌字：

```python
with ThreadPoolExecutor(max_workers=3) as pool:
    # 封装带有 60s 单图超时和异常熔断的 worker
    futures = {pool.submit(_translate_worker, item): item for item in candidate_tasks}
    for i, fut in enumerate(as_completed(futures)):
        # 更新 Translator 基类的 progress_tracker
        pct = 88 + int(6.0 * (i + 1) / total_candidates)
        self.progress_tracker.update(percent=pct, message=f"正在翻译文档内插图 ({i+1}/{total_candidates})...")
```

---

### 4. 交付清单 Manifest 写入（`<stem>.imgtr.json`）

处理完毕后，在产物同级目录下生成审计报告：

```json
{
  "document": "QX027N_Protocol.docx",
  "total_embedded_images": 5,
  "processed_images": 2,
  "skipped_images": 3,
  "details": [
    {
      "image_index": 1,
      "container": "body",
      "display_size_pt": [420.0, 260.0],
      "status": "translated",
      "blocks_count": 8,
      "qc_passed": true
    },
    {
      "image_index": 2,
      "container": "header",
      "display_size_pt": [80.0, 24.0],
      "status": "skipped",
      "reason": "too_small_header_logo"
    }
  ]
}
```

---

## 三、异常与回滚保障

1. **单图熔断保障**：
   - 某张图片若在 OCR 报错、大模型翻译超时（>60s）或触发 QC C10（原图损伤），立即记录警告并保留原图不变，其余图继续处理，绝不中断文档输出。
2. **全局开关快速回滚**：
   - 保持环境变量 `QYUNSLATION_IMAGE_OVERLAY=0` 兼容性，设为 0 时秒退，保持原纯文本翻译行为。

---

## 四、验收标准

1. **多引用隔离测试**：
   - 构造一个 DOCX，页眉与正文引用同一个 ImagePart。执行翻译后，正文设计图被翻译，而页眉 Logo 的图像内容与尺寸完全保持原状。
2. **尺寸门槛过滤测试**：
   - 正文包含一个 400×250pt 的设计图与一个 30×30pt 的小图标，小图标在日志与 Manifest 中被标记为 `too_small` 跳过，大图成功翻译。
3. **版式无损测试**：
   - 译后 DOCX 用 LibreOffice/WPS 打开无报错，图片环绕方式（四周型/嵌入型）无变形偏移。
