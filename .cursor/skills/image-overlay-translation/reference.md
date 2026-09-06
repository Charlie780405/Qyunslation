# 参考数据（SK-Q002）

## 方案设计图-20260728.jpg（4353×2132）

| 指标 | HPD | PLAN-021 | PLAN-022 | PLAN-023 | PLAN-024 | PLAN-025 |
| --- | --- | --- | --- | --- | --- | --- |
| OCR 框 | 2 | 60 | ≥55 | ≥55 | ≥55 | ≥55 |
| 译文命中 | 0/60 | 60/60 | ≥95% | ≥95% | ≥95% | ≥95% |
| 蓝框对比度 | — | 1 | ≥60 | ≥60 | ≥60 | ≥60 |
| solid 命中 | — | ~8/60 | 同左 | ≥55/60 | ≥55/60 | ≥55/60 |
| 蓝框组字号 | — | 各自 | 各自 | 各自 | 8 个全等 | 同左 |
| 脚注组字号 | — | 各自 | 各自 | 各自 | 7 个全等 | 同左 |
| 对齐偏移>12px | — | — | — | ~50/60 | 同左 | ≤1（仅图边界） |
| QC | — | — | — | C1–C6 | +C7a/C7b | +C8 |

### 取色反例（旧 `vals<120`）

| 框 | 背景灰度 | 真实文字灰度 | 旧取色 | 对比度 |
| --- | --- | --- | --- | --- |
| QX027N 蓝 | 84 | 243（白） | 83 | 1 |
| 安慰剂灰 | 129 | 246 | 117 | 12 |
| 筛选期白底 | 248 | 12 | 10 | 238 |

### 纯色误判反例（旧拍平 std）

| 框 | 边框 bg | 拍平 std | 通道 max std | 旧 solid | 新 solid |
| --- | --- | --- | --- | --- | --- |
| QX027N 蓝 | (154,95,33) | ~50 | ~0 | False | True |
| 16周（蹭括号线） | 白+青边 | >12 | 小但 frac 低 | False | True（frac≥0.80） |

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
| `QYUNSLATION_SOLID_STD_MAX` | 按通道纯色 std | 12 |
| `QYUNSLATION_SOLID_FRAC_MIN` | 贴近中位数占比 | 0.80 |
| `QYUNSLATION_AVAIL_W_MULT` | 可用区横向上限倍数 | 3.0 |
| `QYUNSLATION_AVAIL_H_MULT` | 可用区纵向上限倍数 | 1.6 |
| `QYUNSLATION_IMAGE_QC_STRICT` | QC 硬失败抛错 | 0 |
| `QYUNSLATION_TIER_OUTLIER_RATIO` | 比值低于组中位此倍视为 outlier | 0.6 |
| `QYUNSLATION_TIER_RATIO_TOL` | 组间比例允许偏差 | 0.02 |
| `QYUNSLATION_ALIGN_TOL_PX` | C8 成品 vs 计划锚点容差 | 12 |
| `QYUNSLATION_BOLD_AREA_RATIO` | 粗体面积比 | 0.28 |
| `QYUNSLATION_TRANSLATE_BATCH` | 批大小 | 25 |

### 对齐偏移实测（PLAN-025 前 → 后，方案设计图）

| 框 | 旧 dx,dy（可用区居中） | 新 plan_dx,plan_dy |
| --- | --- | --- |
| 随访期/维持期/筛选期/诱导期 | ~182, 0 | ~0, 0 |
| 主要终点 / 分层因素 | 460 / 1125, ~16 | ~0 / 图边界 clamp |
| W12–W52 一行 | dy≈18 统一下沉 | 竖向方差 ≤2px |
