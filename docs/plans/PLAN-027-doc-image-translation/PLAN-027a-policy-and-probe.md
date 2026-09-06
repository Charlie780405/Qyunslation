# PLAN-027a 子计划：判定策略、探针 API 与 Alpha 保真通道

## 一、目标与解决痛点

1. **解决痛点 1（过滤误杀与文字误判）**：
   - 之前简单套用 Hermes 的“色数 ≤ 4 或体积 < 8KB 视为噪声”，导致黑白线框图、高压缩率矢量流程图被直接丢弃；
   - 缺乏语种检测与纯数字过滤，导致图中坐标刻度（0, 10, 20）、药物代码（QX027N）或中译英中原本就是英文的词条被送大模型产生幻觉。
2. **解决痛点 2（Alpha 透明度损毁）**：
   - `image_translate.py` 内部使用 `cv2.imread()` 丢掉第 4 通道，导致透明 PNG 回嵌后变成黑色死斑。
3. **解决痛点 3（预扫描缺乏轻量探针）**：
   - 之前只能调完整的 `translate_image`（调 LLM，耗时 15-30s），无法支撑上传后秒级的文本探针检测。

---

## 二、详细技术规范与接口设计

### 1. `qyunslation/extensions/doc_image_policy.py`（独立、零复杂依赖）

本模块仅依赖 Python 标准库与 `PIL`，供本仓与 PDF 外部环境无缝加载。

```python
@dataclass
class ImageDecision:
    should_translate: bool
    reason: str  # "ok", "too_small", "pure_noise", "no_translatable_text", "already_target_lang"
    translatable_blocks: int
    source_lang: str
    feature_hash: str

def evaluate_image_candidate(
    img_bytes: bytes,
    display_width_pt: float,
    display_height_pt: float,
    target_lang: str = "简体中文",
    page_frac: float | None = None,
    is_header: bool = False
) -> ImageDecision:
    """根据物理显示尺寸、页面占比、像素几何进行快速初筛"""
```

**判据流水线**：
1. **物理显示门槛**：显示长边 < 150pt 或面积 < 25000pt²，判定为图标/项目符号，直接跳过。
2. **整页扫描图保护**：若 `page_frac > 0.90`，判定为扫描底图，交由 HPD 全页链路处理，此处跳过。
3. **低熵与极值长宽比**：极窄横幅（宽高比 > 8 且短边 < 20pt）视为页面分割线，直接跳过。
4. **纯数字与公式门控**：
   - 过滤正则：`r"^[\d\s\.\,\+\-\*\/\=\%\:\;\(\)\[\]℃°\<\>\±]+$"`（纯数字/标点）。
   - 若块内文字全为数字、单位（mg, mL, kg, w, h）、化学式，不计入待译块数。
5. **语种门控**：
   - 中译英任务：若识别出的文字已全是 ASCII 英文（无中文字符），标记为 `already_target_lang`，保留原图不翻译；
   - 英译中任务：若识别文字已含汉字且无待译英文单词，跳过。

---

### 2. sidecar 轻量探针端点：`/service/image-probe`

在 `qyunslation/custom_api.py` 中新增：

```python
@router.post("/image-probe", summary="文档内嵌图片轻量探针（仅OCR不调LLM）")
async def image_probe_endpoint(
    file: UploadFile = File(...),
    target_lang: str = Form("简体中文"),
):
    """
    接收图片文件，仅执行 RapidOCR + 策略判定，耗时控制在 300ms~1.2s。
    返回结构:
    {
        "status": "ok", # "ok" | "skip" | "error"
        "should_translate": bool,
        "reason": str,
        "detected_blocks": int,
        "translatable_blocks": int,
        "detected_lang": str, # "zh" | "en" | "mixed" | "num_only"
        "text_samples": ["Step 1: Induction", "Week 16 Endpoint"]
    }
    """
```
- **超时与错误隔离**：单图探测限时 10 秒；若 RapidOCR 偶发崩溃或超时，返回 `status: "error"`，不抛 500，预扫描前端据此提示“需进入翻译深入解析”。

---

### 3. `image_translate.py` RGBA / Alpha 通道保真改造

1. **输入阶段**：
   - 使用 `PIL.Image.open(BytesIO(data))` 检查模式。若为 `RGBA`、`LA` 或包含透明度调色板（`transparency`），提取原始 `alpha_channel`。
2. **中间计算阶段**：
   - OCR 与 Inpaint 仅在 RGB 3通道（白底合成图）上进行，保证 RapidOCR 与 Otsu 配色的准确性；
3. **输出阶段**：
   - 文字擦除与覆盖后，将原始 `alpha_channel` 重新贴合；
   - 对新绘制的文字带，文字前景 Alpha 置为 255，文字背景保留原图的透明/非透明分布；
   - 导出保持原格式编码（PNG 保持 RGBA，不盲目转 RGB JPEG）。
4. **QC 数据结构升级**：
   - `translate_image_bytes` 改为返回 `(bytes, count, qc_dict)`，将 C1~C10 违规信息向上传递，供文档级 Manifest 汇总。

---

## 三、验收标准

1. **纯数字与英文图例测试**：
   - 输入纯坐标轴图（只有 0, 10, 20...），`image-probe` 准确返回 `translatable_blocks: 0`, `should_translate: false`；
   - 中译英任务输入全英文流程图，探针准确返回 `already_target_lang`，不送 LLM。
2. **透明 PNG 保真测试**：
   - 准备一张透明背景的医学抗体结构图（含文字），经过嵌字后，背景区域透明度保持 0，RGB 区域无黑斑。
3. **性能验收**：
   - `/service/image-probe` 单图耗时稳定在 1.5 秒以内。
