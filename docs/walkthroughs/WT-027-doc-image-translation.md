# WT-027 文档内嵌图片翻译

## 交付摘要

实现 PLAN-027：上传预扫描 + DOCX DrawingML 实例解耦嵌字 + PDF 位图/矢量双策略原位回嵌。

## 关键变更

| 路径 | 说明 |
| --- | --- |
| `qyunslation/extensions/doc_image_policy.py` | 几何/语种/数字判定 |
| `qyunslation/extensions/docx_image_overlay.py` | DrawingML 枚举与克隆回填 |
| `qyunslation/extensions/image_translate.py` | Alpha 保真、probe、QC 三元组返回 |
| `qyunslation/custom_api.py` | `/service/image-probe` |
| `scripts/doc_image_prescan.py` | Tier-1 结构扫描 |
| `scripts/pdf_figure_crop.py` | 矢量安全聚类（Fail-Closed） |
| `scripts/pdf_image_translate.py` | PDF 双策略 SSOT |
| `scripts/apply-pdf2zh-prescan.py` | 左栏预扫描 + 代际锁 |
| `scripts/apply-pdf2zh-docimg.py` | PDF 前置嵌字补丁 |
| `scripts/verify-plan-027.sh` | 自动化验收 |
| `archive/legacy/image_replace.py` | 旧 zip 方案归档 |
| SK-Q002 | 文档内嵌图铁律 23–31 |

## 上线后修正（PLAN-027f）

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| 上传后原文预览渲染进「译文」栏，中栏空白 | Gradio `.column` 默认 `flex-wrap: wrap`，长预览超出剩余高度后另起一列，落到右邻栏坐标 | 中右栏补 `flex-wrap: nowrap` |
| 满是中文的流程图被预扫描报成「无可译文字」 | pdf2zh venv 无 `rapidocr`，`probe_image` 静默回退弱检测器（43 块→0 块） | Tier-2 探针改走 sidecar `/service/image-probe` |
| PDF 内嵌图嵌字质量劣化且从不回退 | 同一根因，本地 OCR 不抛异常所以 sidecar 分支永不触发 | `has_local_ocr()` 能力门控，无能力直接走 sidecar |
| `apply-pdf2zh-prescan.py` 改动不生效 | 补丁「已存在即跳过」，无法随脚本演进 | 改为删旧重插 + 空白规范化，保持幂等 |

## 验收

```bash
bash scripts/verify-plan-027.sh
```

预期：`FAIL=0`，含补丁幂等、Alpha、DOCX 枚举、PDF 守卫、回归 026。

## 部署

```bash
sudo systemctl restart qyunslation-office.service
sudo systemctl restart pdf2zh.service
```

部署 commit：`4ee11a9d569dad5471e3d272f7e29b213ebec2c6`
