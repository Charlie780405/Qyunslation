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
