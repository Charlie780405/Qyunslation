# PLAN-027f 子计划：OCR 引擎可观测性与依赖转正

## 一、目标与解决痛点

1. **解决痛点 1（依赖声明与 import 名不一致）**：
   - `pyproject.toml` 声明 `rapidocr-onnxruntime`（1.x API），代码写 `from rapidocr import RapidOCR`（3.x）；
   - 真正在跑的 `rapidocr 3.6.0` 是 docling 的传递依赖；一旦 docling 被移除或降级，嵌字主链路静默退化。
2. **解决痛点 2（OCR 失败被静默吸收）**：
   - `ocr_image` 在 RapidOCR 缺失/失败时吞掉异常，回退 HPD；流程图同图从 43 块掉到 0 块却不报警。
   - HPD 是远程 `/parse` 版面解析，不是本地 OCR；对流程图会把整图标成 `<BLOCK>image`，适合扫描件整页。
3. **解决痛点 3（跨 venv 能力漂移不可见）**（已上线热修归档）：
   - pdf2zh 与 qyunslation 是独立 venv；Tier-2 / PDF 嵌字若在无 RapidOCR 的进程内跑本地 `probe_image`，会误报「无可译文字」。
   - 热修：`has_local_ocr()` + sidecar `/service/image-probe`；中右栏 `flex-wrap: nowrap` 修预览错位。

本机无 GPU、Ollama 仅有纯文本模型，Vision 只留接口位，不接真实实现。

---

## 二、详细技术规范

### 1. 依赖转正

```toml
# pyproject.toml
"rapidocr>=3.6.0",
"onnxruntime>=1.17.0",   # RapidOCR 运行时必需，上游未声明
"pymupdf>=1.24.0",       # PDF 脚本 / verify 必需
```

- 移除死依赖 `rapidocr-onnxruntime`。
- `uv lock` + `uv sync` 后校验：docling 未降级；同文档探针块数仍为 43/59。

### 2. 引擎注册表（`image_translate.py`）

```python
QYUNSLATION_OCR_ENGINE = auto | rapidocr | hpd | vision   # 默认 auto

def ocr_engine_status(*, refresh=False) -> dict:
    # engines.rapidocr.status ∈ {ok, unavailable, failed}
    # engines.hpd.status      ∈ {ok, unavailable}
    # engines.vision.status   == stub

def ocr_image_with_engine(path) -> tuple[list, str]:
    # 返回 (boxes, engine_actually_used)

def ocr_image_vision(path) -> list:
    raise NotImplementedError(...)  # 禁止静默返回 []
```

**auto 决策**：RapidOCR ok → 跑；零块/unavailable/failed → warning + HPD。默认回退行为不变，只让降级可见。

**Vision 接入契约**（未实现）：DeepSeek grounding `<|det|>[[x1,y1,x2,y2]]` 为 0–999 归一化；`px = int(coord / 999 * dim)`。

### 3. 探针与启动自检

- `probe_image` / `/service/image-probe` 响应增加 `ocr_engine`；错误分支也带该字段。
- `app.py` lifespan 启动打印一次 `OCR capability: {ocr_engine_status()}`。

### 4. 防回归断言（`verify-plan-027.sh` §8d）

- 依赖名与 import 一致；无死依赖。
- `ocr_engine_status` 区分三态；`vision` stub 抛 `NotImplementedError`。
- PIL 合成 12 标签中文图：断言 `engine == "rapidocr"` 且块数 ≥ 8（引擎降级立刻红）。

---

## 三、验收标准

1. `bash scripts/verify-plan-027.sh` → `FAIL=0`，含 §8d。
2. 服务重启后 journalctl 可见 `OCR capability: ... rapidocr ... ok`。
3. `/service/image-probe` 响应含 `"ocr_engine": "rapidocr"`。
4. 实测文档探针块数相对转正前不下降。
