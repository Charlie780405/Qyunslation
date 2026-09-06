# PLAN-024 全屏预览裁切修复与字号层级统一

## 目标

1. 全屏大图不再裁掉底部（访视轴 / 分层因素可见）
2. 同级文字字号统一，组间保持原图比例
3. 判据写入 SK-Q002

## 改动

| 文件 | 作用 |
|------|------|
| `scripts/apply-pdf2zh-viewer.py` | 全屏不嵌套 inner；确定高度链 |
| `qyunslation/extensions/image_translate.py` | `_assign_tiers` / `_assign_tier_sizes` / QC C7 |
| `.cursor/skills/image-overlay-translation/` | 铁律与踩坑 |
| `scripts/verify-plan-024.sh` | 验收 |

## 验收

`bash scripts/verify-plan-024.sh`：蓝框组字号全等、脚注组字号全等、比例偏差≤2%、QC 全绿、回归 023。
