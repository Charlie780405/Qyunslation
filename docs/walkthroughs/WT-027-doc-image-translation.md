# WT-027 文档内嵌图片翻译

## 交付摘要

实现 PLAN-027：上传预扫描 + DOCX DrawingML 实例解耦嵌字 + PDF 位图/矢量双策略原位回嵌；027f 将 OCR 引擎从「静默回退」改为「显式可观测」。

## 关键变更

| 路径 | 说明 |
| --- | --- |
| `qyunslation/extensions/doc_image_policy.py` | 几何/语种/数字判定 |
| `qyunslation/extensions/docx_image_overlay.py` | DrawingML 枚举与克隆回填 |
| `qyunslation/extensions/image_translate.py` | Alpha 保真、probe、OCR 引擎注册表、`ocr_engine` |
| `qyunslation/custom_api.py` | `/service/image-probe`（透传 `ocr_engine`） |
| `qyunslation/app.py` | 启动打印 `ocr_engine_status()` |
| `pyproject.toml` / `uv.lock` | `rapidocr`+`onnxruntime` 转正，去掉死依赖 |
| `scripts/doc_image_prescan.py` | Tier-1 结构扫描 |
| `scripts/pdf_figure_crop.py` | 矢量安全聚类（Fail-Closed） |
| `scripts/pdf_image_translate.py` | PDF 双策略 + `has_local_ocr` |
| `scripts/apply-pdf2zh-prescan.py` | 左栏预扫描 + 代际锁 + sidecar 探针 |
| `scripts/apply-pdf2zh-docimg.py` | PDF 前置嵌字补丁 |
| `scripts/verify-plan-027.sh` | 自动化验收（含 §8d） |
| SK-Q002 | 文档内嵌图铁律 23–35 |

## 上线后热修（027e → 027f 之间）

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| 上传后原文预览渲染进「译文」栏 | Gradio `.column` 默认 `flex-wrap: wrap` | 中右栏 `flex-wrap: nowrap` |
| 中文流程图被预扫描报「无可译文字」 | pdf2zh venv 无 rapidocr，本地探针静默弱回退 | Tier-2 走 sidecar `/service/image-probe` |
| PDF 嵌字劣化且不回退 sidecar | 本地 OCR 不抛异常 | `has_local_ocr()` 能力门控 |
| `apply-pdf2zh-prescan.py` 改动不生效 | 「已存在即跳过」 | 删旧重插 + 空白规范化 |

## PLAN-027f：OCR 引擎可观测

| 项 | 说明 |
| --- | --- |
| 依赖 | `rapidocr>=3.6.0` + `onnxruntime`；移除 `rapidocr-onnxruntime` |
| API | `ocr_engine_status` / `ocr_image_with_engine` / `ocr_image_vision` stub |
| 开关 | `QYUNSLATION_OCR_ENGINE=auto\|rapidocr\|hpd\|vision` |
| 探针 | 响应含 `ocr_engine`；启动 journal 打印能力矩阵 |
| 防回归 | 合成 12 标签中文图断言 `engine==rapidocr` 且块数≥8 |

## 验收

```bash
bash scripts/verify-plan-027.sh
```

预期：`FAIL=0`，含补丁幂等、Alpha、DOCX 枚举、PDF 守卫、§8d OCR 可观测、回归 026。

## 部署

```bash
systemctl --user restart qyunslation-office.service
systemctl --user restart pdf2zh.service
```

部署 commit：（合并后回填）
