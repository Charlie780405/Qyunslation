# PLAN-021 图片翻译丢字修复与预览查看器

## 目标

1. 修复流程图等图片翻译「文字丢失 / 翻译不全」（中译英、英译中均复现）。
2. 为原文/译文预览增加缩放、旋转、拖拽、全屏查看能力。

## 根因（实测）

用 `方案设计图-20260728.jpg`（4353×2132）：

| 环节 | 修复前 | 说明 |
|------|--------|------|
| HPD OCR | 2 框 | 整张流程图被标为 `image`，内部零 OCR |
| RapidOCR | 60 框 / 2s | 已装在 venv，像素坐标，置信度 ≥0.83 |
| LLM | content=0 | `/no_think` 无效；thinking 烧光 `num_predict=2000` |
| `think:false` | 66 token 正常输出 | API 参数可关思考 |
| 渲染 | 先全擦后条件画 | `trans` 空 → 净删字 |

## 改动

| 文件 | 作用 |
|------|------|
| `qyunslation/extensions/image_translate.py` | RapidOCR 主路径 + HPD 回退；`think:false` + 25 条分批 + 单条重试；只擦重绘框；缺译保留原像素；字号二分+换行；返回真实绘制数 |
| `qyunslation/translator/ai_translator/docx_translator.py` | 内嵌图透传 `to_lang` |
| `qyunslation/custom_api.py` | `/image-translate` 接受 `to_lang` Form |
| `qyunslation/extensions/image_replace.py` | CLI 路径补 `to_lang` |
| `scripts/apply-pdf2zh-viewer.py` | 内嵌工具条 + 全屏查看器（img/HTML/PDF canvas） |
| `scripts/pdf2zh.service` | 链尾挂 viewer 补丁 |
| `scripts/verify-plan-021.sh` | 验收 |

## 验收门槛

- OCR ≥ 55 框（该流程图）
- 译文命中率 ≥ 95%
- 缺译框不净擦除
- 中译英 / 英译中各通
- viewer 补丁幂等；017–020 回归通过
