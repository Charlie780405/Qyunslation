# 参考数据（SK-Q002）

## 方案设计图-20260728.jpg（4353×2132）

| 指标 | HPD | RapidOCR + PLAN-021 | PLAN-022 目标 |
| --- | --- | --- | --- |
| OCR 框 | 2 | 60 | ≥55 |
| 译文命中 | 0/60 | 60/60 | ≥95% |
| 蓝框对比度 | — | 1（旧取色） | ≥60 |
| 安慰剂灰框对比度 | — | 12 | ≥60 |

### 取色反例（旧 `vals<120`）

| 框 | 背景灰度 | 真实文字灰度 | 旧取色 | 对比度 |
| --- | --- | --- | --- | --- |
| QX027N 蓝 | 84 | 243（白） | 83 | 1 |
| 安慰剂灰 | 129 | 246 | 117 | 12 |
| 筛选期白底 | 248 | 12 | 10 | 238 |

## 诊断片段

```python
from qyunslation.extensions.image_translate import ocr_image, _analyze_box_style
import cv2
img = cv2.imread(path)
for i, b in enumerate(ocr_image(path), 1):
    st = _analyze_box_style(img[b[1]:b[3], b[0]:b[2]])
    print(i, b[4][:20], st["contrast"], st["align"], st["bold"], st["solid"])
```

## 环境变量

| 键 | 作用 | 默认 |
| --- | --- | --- |
| `QYUNSLATION_FONT` | Regular 字面 | `NotoSansSC-Regular.otf` |
| `QYUNSLATION_FONT_BOLD` | Bold 字面 | `NotoSansSC-Bold.otf` |
| `QYUNSLATION_CONTRAST_MIN` | 强制黑白阈值 | 60 |
| `QYUNSLATION_SOLID_STD_MAX` | 纯色判定 | 12 |
| `QYUNSLATION_BOLD_AREA_RATIO` | 粗体面积比 | 0.28 |
| `QYUNSLATION_TRANSLATE_BATCH` | 批大小 | 25 |
